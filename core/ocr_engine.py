import base64
import requests
import logging
import re
import os
from typing import List

from utils.config import ConfigManager
from models.document import TranslationBlock

logger = logging.getLogger("AiProofAgent.OCREngine")

class PaddleOCREngine:
    def __init__(self, config_path="config.yaml"):
        cfg = ConfigManager(config_path)
        self.api_url = cfg.get("ocr.api_url", "https://ych83fn6yaveg1y3.aistudio-app.com/layout-parsing")
        self.token = cfg.get("ocr.token", "52621de9cc8d22bd45e1cce14789b107191bebca")
        self.headers = {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json"
        }

    def process_pdf(self, file_path: str) -> List[TranslationBlock]:
        """
        处理 PDF 文件并返回分段好的 TranslationBlock 列表。
        """
        logger.info(f"开始使用 PaddleOCR-VL-1.5 处理 PDF: {file_path}")
        
        with open(file_path, "rb") as file:
            file_bytes = file.read()
            file_data = base64.b64encode(file_bytes).decode("ascii")

        # 提取去除了数字的文档名，作为段落 Key 的前缀
        doc_name = os.path.basename(file_path).split('.')[0]
        doc_name = re.sub(r'\d+', '', doc_name).strip(' _-')
        if not doc_name: doc_name = "doc"

        # 根据配置.md要求的参数严格设定
        # 注意：服务端已开启 max_num_input_imgs: null 取消页数限制，此处直接全量上传
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

        try:
            response = requests.post(self.api_url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            result = response.json().get("result", {})
            layout_results = result.get("layoutParsingResults", [])
            
            all_blocks = []
            for i, res in enumerate(layout_results):
                page_num = i + 1
                markdown_data = res.get("markdown", {})
                text = markdown_data.get("text", "")
                
                # 解析Markdown文本为按“页码_段落序号”对应的结构块
                page_blocks = self._parse_markdown_to_blocks(text, page_num, doc_name)
                all_blocks.extend(page_blocks)
            
            logger.info(f"PDF 处理完成，共解析 {len(layout_results)} 页，提取 {len(all_blocks)} 个段落/表格块。")
            return all_blocks
        
        except requests.exceptions.RequestException as e:
            logger.error(f"PaddleOCR 请求失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"响应内容: {e.response.text}")
            raise e

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