import base64
import requests
import logging
import re
import os
import io
import json
import time
from typing import List

from utils.config import ConfigManager
from models.document import TranslationBlock

logger = logging.getLogger("AiProofAgent.OCREngine")

try:
    from PyPDF2 import PdfReader, PdfWriter
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    logger.warning("PyPDF2 not available, PDF splitting will not work")

try:
    from Cryptodome.Cipher import AES
    PYCRYPTODOME_AVAILABLE = True
except ImportError:
    PYCRYPTODOME_AVAILABLE = False
    logger.warning("PyCryptodome not available, encrypted PDF files may not work")

class PaddleOCREngine:
    def __init__(self, config_path="config.yaml"):
        cfg = ConfigManager(config_path)
        self.api_url = cfg.get("ocr.api_url", "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs")
        self.token = cfg.get("ocr.token")
        self.max_batch_pages = cfg.get("ocr.max_batch_pages", 90)
        self.model = cfg.get("ocr.model", "PaddleOCR-VL-1.6")
        self.headers = {
            "Authorization": f"bearer {self.token}",
        }

    def process_pdf(self, file_path: str) -> List[TranslationBlock]:
        """
        处理 PDF 文件并返回分段好的 TranslationBlock 列表。

        改进点：
        1. 支持最后不足 10 页的批次，避免 91 页这类 PDF 在最后 1 页失败。
        2. 对 file_path / PDF 读取 / batch 配置做校验。
        3. OCR 返回空块时视为“本批处理成功但未提取到文本”，不中断整体流程。
        4. 日志页码严格使用处理前保存的区间，避免出现“91 到 90 页”。
        5. 分批失败时逐步缩小批大小，直到 1 页，提升健壮性。
        """
        logger.info(f"开始使用 {self.model} 处理 PDF: {file_path}")

        if not PYPDF2_AVAILABLE:
            logger.error("PyPDF2 not installed, cannot process PDF in batches")
            raise ImportError("PyPDF2 is required for PDF batch processing. Install with: pip install PyPDF2")

        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path 不能为空，且必须是字符串")

        file_path = os.path.abspath(file_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF 文件不存在: {file_path}")
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"路径不是文件: {file_path}")
        if not file_path.lower().endswith(".pdf"):
            logger.warning(f"输入文件扩展名不是 .pdf，但仍尝试按 PDF 处理: {file_path}")

        # 读取 PDF 获取总页数
        try:
            reader = PdfReader(file_path)
            total_pages = len(reader.pages)
        except Exception as e:
            logger.exception("读取 PDF 失败")
            raise Exception(f"无法读取 PDF：{e}") from e

        if total_pages <= 0:
            raise Exception("PDF 没有可处理的页面")

        logger.info(f"PDF 总页数: {total_pages}")

        # 规范化 batch 配置
        try:
            max_batch_pages = int(self.max_batch_pages)
        except Exception:
            logger.warning(f"ocr.max_batch_pages={self.max_batch_pages!r} 非法，回退为 90")
            max_batch_pages = 90

        if max_batch_pages <= 0:
            logger.warning(f"ocr.max_batch_pages={max_batch_pages} 非法，回退为 1")
            max_batch_pages = 1

        # 提取去除了数字的文档名，作为段落 Key 的前缀
        doc_name = os.path.splitext(os.path.basename(file_path))[0]
        doc_name = re.sub(r"\d+", "", doc_name).strip(" _-")
        if not doc_name:
            doc_name = "doc"

        all_blocks: List[TranslationBlock] = []
        current_page = 0  # 0-based
        max_retries = 3

        def _build_candidate_batch_sizes(initial_size: int) -> List[int]:
            """
            生成一组降级批大小：
            例如 initial=37 -> [37, 27, 17, 7, 6, 5, 4, 3, 2, 1]
            例如 initial=90 -> [90, 80, 70, ..., 10, 9, 8, ..., 1]
            """
            sizes = []
            size = initial_size

            while size > 10:
                sizes.append(size)
                size -= 10

            if size > 0:
                sizes.append(size)

            # 再把更小的补齐到 1，保证最后单页也能试
            last = sizes[-1] if sizes else initial_size
            for s in range(last - 1, 0, -1):
                sizes.append(s)

            # 去重 + 过滤非法值
            deduped = []
            seen = set()
            for s in sizes:
                if s >= 1 and s not in seen:
                    deduped.append(s)
                    seen.add(s)
            return deduped

        while current_page < total_pages:
            remaining_pages = total_pages - current_page
            initial_batch_size = min(max_batch_pages, remaining_pages)
            candidate_batch_sizes = _build_candidate_batch_sizes(initial_batch_size)

            logger.info(
                f"当前进度：已完成 {current_page}/{total_pages} 页，"
                f"准备从第 {current_page + 1} 页开始处理，初始批大小={initial_batch_size}"
            )

            batch_done = False
            last_error = None

            for candidate_size in candidate_batch_sizes:
                start_page = current_page
                end_page = min(start_page + candidate_size, total_pages)  # end_page 为右开边界
                page_count = end_page - start_page

                if page_count <= 0:
                    continue

                human_start = start_page + 1
                human_end = end_page  # 因为右开边界 end_page 对应人类页码正好就是最后一页

                logger.info(f"尝试处理第 {human_start} 到 {human_end} 页 (共 {page_count} 页)")

                try:
                    pdf_bytes = self._extract_pages(file_path, start_page, end_page)
                except Exception as e:
                    last_error = e
                    if "PyCryptodome is required for AES algorithm" in str(e):
                        logger.error(f"提取第 {human_start} 到 {human_end} 页失败: PDF文件可能已加密，需要安装PyCryptodome库。请运行: pip install pycryptodome")
                    else:
                        logger.warning(f"提取第 {human_start} 到 {human_end} 页失败: {e}")
                    continue

                if not pdf_bytes:
                    last_error = Exception("提取得到空 PDF 字节流")
                    logger.warning(f"提取第 {human_start} 到 {human_end} 页得到空字节流，将尝试更小批次")
                    continue

                for attempt in range(1, max_retries + 1):
                    try:
                        # 这里直接把 start_page 作为页偏移传入
                        # 因为 _process_pdf_batch() 内 actual_page_num = page_offset + i + 1
                        # 所以传 start_page 后，页码将正确映射为真实 PDF 页码
                        blocks = self._process_pdf_batch(
                            pdf_bytes, start_page, end_page, doc_name, start_page
                        )

                        if blocks is None:
                            blocks = []

                        if not isinstance(blocks, list):
                            raise TypeError(
                                f"_process_pdf_batch 返回值类型错误，应为 list，实际为 {type(blocks).__name__}"
                            )

                        all_blocks.extend(blocks)

                        # 注意：无论 blocks 是否为空，只要 OCR 调用成功返回，就视为这一批处理成功
                        # 否则会把“空白页/图片页/未识别到文本”的正常情况误判为失败
                        current_page = end_page
                        batch_done = True

                        logger.info(
                            f"成功处理第 {human_start} 到 {human_end} 页，提取 {len(blocks)} 个块"
                        )
                        if len(blocks) == 0:
                            logger.warning(
                                f"第 {human_start} 到 {human_end} 页未提取到文本块，已按空结果继续"
                            )
                        break

                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"处理第 {human_start} 到 {human_end} 页失败，"
                            f"第 {attempt}/{max_retries} 次尝试异常: {e}"
                        )

                if batch_done:
                    break

                logger.error(
                    f"处理第 {human_start} 到 {human_end} 页失败，将缩小批大小后继续重试"
                )

            if not batch_done:
                fail_page = current_page + 1
                logger.error(f"无法处理第 {fail_page} 页及之后的页面")
                if last_error is not None:
                    raise Exception(
                        f"PDF 处理失败：无法解析第 {fail_page} 页及之后的页面；最后一次错误：{last_error}"
                    ) from last_error
                raise Exception(f"PDF 处理失败：无法解析第 {fail_page} 页及之后的页面")

        logger.info(f"PDF 处理完成，共解析 {total_pages} 页，提取 {len(all_blocks)} 个段落/表格块。")
        return all_blocks
    
    def _extract_pages(self, file_path: str, start_page: int, end_page: int) -> bytes:
        """提取 PDF 的指定页面范围，返回字节数据"""
        reader = PdfReader(file_path)
        writer = PdfWriter()
        
        for i in range(start_page, end_page):
            if i < len(reader.pages):
                writer.add_page(reader.pages[i])
        
        # 写入内存缓冲区
        output_buffer = io.BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)
        
        return output_buffer.read()
    
    def _process_pdf_batch(self, pdf_bytes: bytes, start_page: int, end_page: int, doc_name: str, page_offset: int) -> List[TranslationBlock]:
        """处理一批 PDF 页面（使用 v1.6 API）"""
        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }
        
        data = {
            "model": self.model,
            "optionalPayload": json.dumps(optional_payload)
        }
        
        files = {"file": ("batch.pdf", pdf_bytes, "application/pdf")}
        
        job_response = requests.post(self.api_url, headers=self.headers, data=data, files=files)
        job_response.raise_for_status()
        
        job_id = job_response.json()["data"]["jobId"]
        logger.info(f"Job submitted successfully. job id: {job_id}")
        
        jsonl_url = self._poll_job_result(job_id)
        
        if not jsonl_url:
            raise Exception("Failed to get result URL from job")
        
        jsonl_response = requests.get(jsonl_url)
        jsonl_response.raise_for_status()
        
        lines = jsonl_response.text.strip().split('\n')
        
        all_blocks = []
        # 使用全局页面计数器，确保页码从page_offset+1开始正确递增
        global_page_counter = page_offset + 1
        
        for i, line in enumerate(lines, start=0):
            line = line.strip()
            if not line:
                continue
            
            result = json.loads(line)["result"]
            layout_results = result.get("layoutParsingResults", [])
            
            # 处理每个页面的布局结果
            # 使用全局页面计数器确保页码正确递增，避免多个layout_results共用同一页码
            for j, res in enumerate(layout_results):
                # 尝试从OCR结果中获取实际页码，如果没有则使用全局计数器
                page_number = res.get("pageNumber") or res.get("page_number") or res.get("page")
                if page_number:
                    actual_page_num = int(page_number)
                else:
                    # 使用全局计数器，确保每个layout_result都有唯一的页码
                    actual_page_num = global_page_counter
                
                # 递增全局计数器，为下一个页面准备
                global_page_counter += 1
                
                markdown_data = res.get("markdown", {})
                text = markdown_data.get("text", "")
                
                page_blocks = self._parse_markdown_to_blocks(text, actual_page_num, doc_name)
                all_blocks.extend(page_blocks)
        
        return all_blocks
    
    def _poll_job_result(self, job_id: str) -> str:
        """轮询获取 OCR 任务结果"""
        while True:
            job_result_response = requests.get(f"{self.api_url}/{job_id}", headers=self.headers)
            job_result_response.raise_for_status()
            
            data = job_result_response.json()["data"]
            state = data["state"]
            
            if state == 'pending':
                logger.info("The current status of the job is pending")
            elif state == 'running':
                try:
                    total_pages = data['extractProgress']['totalPages']
                    extracted_pages = data['extractProgress']['extractedPages']
                    logger.info(f"The current status of the job is running, total pages: {total_pages}, extracted pages: {extracted_pages}")
                except KeyError:
                    logger.info("The current status of the job is running...")
            elif state == 'done':
                extracted_pages = data['extractProgress']['extractedPages']
                start_time = data['extractProgress']['startTime']
                end_time = data['extractProgress']['endTime']
                logger.info(f"Job completed, successfully extracted pages: {extracted_pages}, start time: {start_time}, end time: {end_time}")
                return data['resultUrl']['jsonUrl']
            elif state == "failed":
                error_msg = data['errorMsg']
                raise Exception(f"Job failed, failure reason: {error_msg}")
            
            time.sleep(5)

    def _parse_markdown_to_blocks(self, text: str, page_num: int, doc_name: str) -> List[TranslationBlock]:
        """
        将包含表格和段落标题的整页 Markdown 按照逻辑块拆分，
        生成 TranslationBlock 模型对象。
        """
        blocks = []
        if not text:
            return blocks
            
        # 初步以双换行符进行拆分段落，这可以保证表格和普通段落、标题被分割开
        raw_paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        block_num = 1
        for para in raw_paragraphs:
            # 过滤纯图片内容
            clean_text = re.sub(r'<img[^>]*>', '', para)
            clean_text = re.sub(r'<div[^>]*>', '', clean_text)
            clean_text = re.sub(r'</div\s*>', '', clean_text)
            clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', clean_text)
            
            if not clean_text.strip():
                continue  # 跳过纯图片块
                
            block_key = f"{doc_name}_P{page_num:03d}_B{block_num:03d}"
            
            block = TranslationBlock(
                key=block_key,
                page=page_num,
                block_num=block_num,
                en_block=para  # 此处先将 OCR 解析的内容作为原文本存入
            )
            blocks.append(block)
            block_num += 1
            
        return blocks
