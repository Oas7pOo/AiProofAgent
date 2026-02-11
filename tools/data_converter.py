import pandas as pd
import os
import re
# 假设你的工具函数在同级目录的 io_utils.py 中
from .io_utils import read_csv_schema, load_json, save_json
from .ocr_client import PaddleAPIOcr 

class DataConverter:
    def __init__(self, config=None):
        self.ocr_client = None
        if config and config.get('ocr'):
            ocr_cfg = config['ocr']
            url = ocr_cfg.get('api_url')
            token = ocr_cfg.get('token')
            if url and token:
                self.ocr_client = PaddleAPIOcr(api_url=url, token=token)

    def _is_junk_block(self, text):
        """过滤 OCR 产生的 HTML 垃圾块或空白内容"""
        if re.search(r'<img\s+src=', text, re.IGNORECASE):
            return True
        if re.search(r'<div', text, re.IGNORECASE):
            return True
        # 如果不包含任何文字或数字（纯标点符号/空格）
        if not re.search(r'[\w\u4e00-\u9fa5]', text):
            return True
        return False

    def _generate_blocks_from_page(self, page_text, file_prefix, page_num):
        """将单页 Markdown 按段落切分为结构化数据"""
        # 按双换行切分段落
        blocks = re.split(r'\n\s*\n', page_text)
        results = []
        
        block_idx = 1
        for b in blocks:
            text = b.strip()
            if not text: continue
            
            if self._is_junk_block(text):
                continue

            # 生成唯一标识 Key: Filename_P001_B001
            key_str = f"{file_prefix}_P{page_num:03d}_B{block_idx:03d}"

            results.append({
                "key": key_str,
                "original": text,
                "translation": "",
                "stage": 0
            })
            block_idx += 1
            
        return results

    def pdf_to_file(self, pdf_path, out_path, out_format='json'):
        if not self.ocr_client:
            raise ValueError("OCR client not initialized. Check config.")
        
        print(f"[Convert] Starting OCR for: {pdf_path}")
        
        # 1. 准备 Key 前缀
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        safe_prefix = re.sub(r'[^a-zA-Z\u4e00-\u9fa5]', '_', base_name)
        safe_prefix = re.sub(r'_+', '_', safe_prefix).strip('_')
        if not safe_prefix: safe_prefix = "DOC"

        # 2. 调用 OCR
        page_texts = self.ocr_client.run_ocr(pdf_path)
        
        # 3. 逐页生成 Block
        all_data = []
        for page_idx, page_text in enumerate(page_texts):
            page_num = page_idx + 1
            page_blocks = self._generate_blocks_from_page(page_text, safe_prefix, page_num)
            all_data.extend(page_blocks)
        
        # 4. 保存结果
        if out_format == 'json':
            save_json(out_path, all_data)
        else:
            df = pd.DataFrame(all_data)
            cols = ['key', 'original', 'translation', 'stage']
            df[cols].to_csv(out_path, index=False, encoding='utf-8-sig')
            
        print(f"[Convert] Success. Generated {len(all_data)} blocks.")
        return len(all_data)

    def csv_to_json(self, csv_path, json_path):
        try:
            df = read_csv_schema(
                csv_path,
                schema=["key", "original", "translation", "stage"],
                drop_first_row="auto",
                treat_first_row_as_header="auto",
                strict=True,
            )

            data_list = []
            for _, row in df.iterrows():
                item = row.to_dict()

                item["key"] = str(item.get("key", "")).strip()
                item["original"] = str(item.get("original", "")).strip()
                item["translation"] = str(item.get("translation", "")).strip()

                # stage 允许缺失/空
                try:
                    item["stage"] = int(str(item.get("stage", "0")).strip() or "0")
                except Exception:
                    item["stage"] = 0

                data_list.append(item)

            save_json(json_path, data_list)
            return len(data_list)

        except Exception as e:
            raise RuntimeError(f"CSV->JSON Error: {e}")

    def json_to_csv(self, json_path, csv_path):
        """JSON 数据扁平化导出为 CSV"""
        try:
            data_list = load_json(json_path)
            if not data_list: raise ValueError("JSON file empty")
            
            df = pd.DataFrame(data_list)
            cols = ['key', 'original', 'translation', 'stage']
            # 过滤掉不存在的列，确保不崩溃
            final_cols = [c for c in cols if c in df.columns]
            
            df[final_cols].to_csv(csv_path, index=False, encoding='utf-8-sig')
            return len(data_list)
        except Exception as e:
            raise RuntimeError(f"JSON->CSV Error: {str(e)}")