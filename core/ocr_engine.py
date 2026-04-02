import base64
import requests
import logging
import re
import os
import io
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

class PaddleOCREngine:
    def __init__(self, config_path="config.yaml"):
        cfg = ConfigManager(config_path)
        self.api_url = cfg.get("ocr.api_url", "https://ych83fn6yaveg1y3.aistudio-app.com/layout-parsing")
        self.token = cfg.get("ocr.token", "52621de9cc8d22bd45e1cce14789b107191bebca")
        self.max_batch_pages = cfg.get("ocr.max_batch_pages", 90)
        self.headers = {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json"
        }

    def process_pdf(self, file_path: str) -> List[TranslationBlock]:
        """
        处理 PDF 文件并返回分段好的 TranslationBlock 列表。
        使用分批处理策略：先尝试处理 max_batch_pages 页，如果失败则减少页数重试。
        """
        logger.info(f"开始使用 PaddleOCR-VL-1.5 处理 PDF: {file_path}")
        
        if not PYPDF2_AVAILABLE:
            logger.error("PyPDF2 not installed, cannot process PDF in batches")
            raise ImportError("PyPDF2 is required for PDF batch processing. Install with: pip install PyPDF2")
        
        # 读取 PDF 获取总页数
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        logger.info(f"PDF 总页数: {total_pages}")
        
        # 提取去除了数字的文档名，作为段落 Key 的前缀
        doc_name = os.path.basename(file_path).split('.')[0]
        doc_name = re.sub(r'\d+', '', doc_name).strip(' _-')
        if not doc_name: doc_name = "doc"
        
        all_blocks = []
        current_page = 0
        page_offset = 0  # 用于调整页码
        
        while current_page < total_pages:
            # 计算本次要处理的页面范围
            remaining_pages = total_pages - current_page
            batch_size = min(self.max_batch_pages, remaining_pages)
            
            # 尝试处理当前批次
            success = False
            current_batch_size = batch_size
            max_retries = 3
            
            while current_batch_size >= 10 and not success:
                end_page = min(current_page + current_batch_size, total_pages)
                logger.info(f"尝试处理第 {current_page + 1} 到 {end_page} 页 (共 {current_batch_size} 页)")
                
                # 提取当前批次的页面
                pdf_bytes = self._extract_pages(file_path, current_page, end_page)
                
                # 尝试解析
                for attempt in range(max_retries):
                    try:
                        blocks = self._process_pdf_batch(pdf_bytes, current_page, end_page, doc_name, page_offset)
                        if blocks:
                            all_blocks.extend(blocks)
                            success = True
                            page_offset += (end_page - current_page)
                            current_page = end_page
                            logger.info(f"成功处理第 {current_page - (end_page - current_page) + 1} 到 {end_page} 页，提取 {len(blocks)} 个块")
                            break
                    except Exception as e:
                        logger.warning(f"第 {attempt + 1} 次尝试失败: {e}")
                        if attempt == max_retries - 1:
                            logger.error(f"处理第 {current_page + 1} 到 {end_page} 页失败，将减少页数重试")
                
                if not success:
                    # 减少页数重试
                    current_batch_size -= 10
                    if current_batch_size < 10:
                        logger.error(f"无法处理第 {current_page + 1} 页及之后的页面，即使减少到 10 页也失败")
                        raise Exception(f"PDF 处理失败：第 {current_page + 1} 页无法解析")
            
            if not success:
                logger.error(f"无法处理第 {current_page + 1} 页及之后的页面")
                raise Exception(f"PDF 处理失败：无法解析第 {current_page + 1} 页及之后的页面")
        
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
        """处理一批 PDF 页面"""
        file_data = base64.b64encode(pdf_bytes).decode("ascii")
        
        payload = {
            "file": file_data,
            "fileType": 0,                    # 0表示PDF文件
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
            "useLayoutDetection": True,       # 开启版面区域检测排序
            "layoutNms": True,                # 开启NMS后处理移除重叠框
            "restructurePages": True,         # 重构多页结果
            "mergeTables": True,              # 跨页表格合并
            "relevelTitles": True,            # 段落标题级别识别
            "prettifyMarkdown": True,         # Markdown美化
            "visualize": False                # 不返回图像，减少返回时间
        }
        
        response = requests.post(self.api_url, json=payload, headers=self.headers)
        response.raise_for_status()
        
        result = response.json().get("result", {})
        layout_results = result.get("layoutParsingResults", [])
        
        all_blocks = []
        for i, res in enumerate(layout_results):
            # 计算实际页码（加上偏移量）
            actual_page_num = page_offset + i + 1
            markdown_data = res.get("markdown", {})
            text = markdown_data.get("text", "")
            
            # 解析Markdown文本为按"页码_段落序号"对应的结构块
            page_blocks = self._parse_markdown_to_blocks(text, actual_page_num, doc_name)
            all_blocks.extend(page_blocks)
        
        return all_blocks

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
