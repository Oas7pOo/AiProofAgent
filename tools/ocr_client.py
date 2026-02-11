import base64
import requests

class PaddleAPIOcr:
    def __init__(self, api_url, token):
        self.api_url = api_url
        self.token = token

    def run_ocr(self, file_path):
        """
        执行 OCR 任务并返回分页文本列表 ["page1_text", "page2_text", ...]
        """
        # === 1. 读取并编码文件 ===
        try:
            with open(file_path, "rb") as file:
                file_bytes = file.read()
                file_data = base64.b64encode(file_bytes).decode("ascii")
        except Exception as e:
            raise RuntimeError(f"Read file error: {e}")

        # === 2. 提交任务 ===
        headers = {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json"
        }

        payload = {
            "file": file_data,
            "fileType": 0, # 0=PDF, 1=Image
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        print(f"[OCR] Uploading file to {self.api_url}...")
        try:
            submit_resp = requests.post(self.api_url, json=payload, headers=headers)
            
            if submit_resp.status_code != 200:
                raise RuntimeError(f"OCR Submit Failed (Status {submit_resp.status_code}): {submit_resp.text}")
            
            submit_data = submit_resp.json()
            
            # === 3. 解析返回结构 ===
            if "result" not in submit_data or "layoutParsingResults" not in submit_data["result"]:
                print(f"[OCR] Unexpected API response structure: {submit_data}")
                return []

            parsing_results = submit_data["result"]["layoutParsingResults"]
            
            # 按页码排序，确保内容顺序正确
            parsing_results.sort(key=lambda x: x.get("page", 0))
            
            # 提取每一页的 markdown 文本
            page_texts = []
            for item in parsing_results:
                text = item.get("markdown", {}).get("text", "")
                page_texts.append(text)
            
            print(f"[OCR] Successfully processed {len(page_texts)} pages.")
            return page_texts

        except Exception as e:
            raise RuntimeError(f"OCR Network or Parsing Error: {e}")