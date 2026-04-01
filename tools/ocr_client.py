import os
import time
import base64
import shutil
import requests
import tempfile
from typing import List, Tuple
from pypdf import PdfReader, PdfWriter


class PaddleAPIOcr:
    def __init__(
        self,
        api_url,
        token,
        max_batch_pages=90,
        min_batch_pages=10,
        step_pages=10,
        timeout=600,
        max_retries=3,
        retry_interval=60,
    ):
        """
        参数说明：
        - max_batch_pages: 每段起始尝试的最大页数，例如 90
        - min_batch_pages: 最小退让页数，例如 10
        - step_pages: 每次失败后递减多少页，例如 10
        - timeout: 单次请求超时时间（秒）
        - max_retries: 每个页数尝试次数，例如 3
        - retry_interval: 重试等待时间（秒）
        """
        self.api_url = api_url
        self.token = token
        self.max_batch_pages = max_batch_pages
        self.min_batch_pages = min_batch_pages
        self.step_pages = step_pages
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_interval = retry_interval

        if self.max_batch_pages < self.min_batch_pages:
            raise ValueError("max_batch_pages must be >= min_batch_pages")
        if self.step_pages <= 0:
            raise ValueError("step_pages must be > 0")

    def _build_headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, file_data: str):
        return {
            "file": file_data,
            "fileType": 0,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
            "useLayoutDetection": False,
            "restructurePages": True,
            "mergeTables": True,
            "relevelTitles": True,
            "prettifyMarkdown": True,
            "visualize": False,
        }

    def _pdf_to_base64(self, pdf_path: str) -> str:
        try:
            with open(pdf_path, "rb") as file:
                file_bytes = file.read()
            return base64.b64encode(file_bytes).decode("ascii")
        except Exception as e:
            raise RuntimeError(f"Read file error: {e}")

    def _extract_page_texts_from_response(self, resp: requests.Response) -> List[str]:
        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"OCR response json parse error: {e}")

        if data.get("errorCode") not in (None, 0):
            raise RuntimeError(
                f"OCR service error: errorCode={data.get('errorCode')}, "
                f"errorMsg={data.get('errorMsg')}, logId={data.get('logId')}"
            )

        if "result" not in data or "layoutParsingResults" not in data["result"]:
            raise RuntimeError(f"Unexpected API response structure: {data}")

        parsing_results = data["result"]["layoutParsingResults"]
        if not isinstance(parsing_results, list):
            raise RuntimeError("layoutParsingResults is not a list")

        page_texts = []
        for item in parsing_results:
            text = item.get("markdown", {}).get("text", "")
            if text is None:
                text = ""
            page_texts.append(text)

        return page_texts

    def _ocr_single_pdf_once(self, pdf_path: str) -> List[str]:
        """
        单次请求，不包含重试。
        """
        file_data = self._pdf_to_base64(pdf_path)
        headers = self._build_headers()
        payload = self._build_payload(file_data)

        print(f"[OCR] Uploading file to {self.api_url}: {pdf_path}")

        resp = requests.post(
            self.api_url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"OCR Submit Failed (Status {resp.status_code}): {resp.text}"
            )

        page_texts = self._extract_page_texts_from_response(resp)
        print(f"[OCR] Successfully processed {len(page_texts)} pages from {pdf_path}.")
        return page_texts

    def _ocr_single_pdf_with_retries(
        self,
        pdf_path: str,
        batch_size: int,
        start_page: int,
        end_page: int,
    ) -> List[str]:
        """
        对指定 pdf 分段，用当前 batch_size 重试 max_retries 次。
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                print(
                    f"[OCR] Trying pages {start_page}-{end_page} "
                    f"(batch_size={batch_size}), attempt {attempt}/{self.max_retries}"
                )
                return self._ocr_single_pdf_once(pdf_path)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_error = RuntimeError(
                    f"Network error for pages {start_page}-{end_page}: {e}"
                )
                print(f"[OCR] Attempt {attempt}/{self.max_retries} failed: {last_error}")

            except requests.exceptions.RequestException as e:
                # requests 的其他异常也记为一次失败
                last_error = RuntimeError(
                    f"Request exception for pages {start_page}-{end_page}: {e}"
                )
                print(f"[OCR] Attempt {attempt}/{self.max_retries} failed: {last_error}")

            except Exception as e:
                # 包括 500 / 504 / 解析错误等，全部按一次失败处理
                last_error = RuntimeError(
                    f"Pages {start_page}-{end_page}, batch_size={batch_size}, error: {e}"
                )
                print(f"[OCR] Attempt {attempt}/{self.max_retries} failed: {last_error}")

            if attempt < self.max_retries:
                print(f"[OCR] Waiting {self.retry_interval} seconds before retry...")
                time.sleep(self.retry_interval)

        raise RuntimeError(
            f"Failed after {self.max_retries} attempts for pages "
            f"{start_page}-{end_page} (batch_size={batch_size}): {last_error}"
        )

    def _write_pdf_range(
        self,
        reader: PdfReader,
        start_idx: int,
        end_idx: int,
        temp_dir: str,
    ) -> str:
        """
        从 reader 中截取 [start_idx, end_idx]（0-based, 闭区间）写到临时 pdf，返回路径。
        """
        writer = PdfWriter()
        for page_num in range(start_idx, end_idx + 1):
            writer.add_page(reader.pages[page_num])

        split_path = os.path.join(temp_dir, f"split_{start_idx + 1}_{end_idx + 1}.pdf")
        with open(split_path, "wb") as f:
            writer.write(f)

        return split_path

    def _normalize_page_texts(self, page_texts: List[str], expected_count: int) -> List[str]:
        """
        保证返回页数和 expected_count 一致：
        - 少了补空串
        - 多了截断
        """
        if len(page_texts) < expected_count:
            page_texts = page_texts + [""] * (expected_count - len(page_texts))
        elif len(page_texts) > expected_count:
            page_texts = page_texts[:expected_count]
        return page_texts

    def _generate_batch_sizes(self) -> List[int]:
        """
        生成批次尝试序列：
        90,80,70,...,10
        """
        sizes = []
        size = self.max_batch_pages
        while size >= self.min_batch_pages:
            sizes.append(size)
            size -= self.step_pages

        # 确保 min_batch_pages 一定在列表里
        if sizes[-1] != self.min_batch_pages:
            sizes.append(self.min_batch_pages)

        # 去重并保持顺序
        result = []
        seen = set()
        for s in sizes:
            if s not in seen and s > 0:
                result.append(s)
                seen.add(s)
        return result

    def run_ocr(self, file_path: str) -> List[str]:
        """
        执行 OCR，核心策略：
        1. 从未 OCR 的最开始页面开始
        2. 优先尝试 90 页
        3. 每个页数先试 3 次
        4. 失败则降到 80、70 ... 10
        5. 如果 10 页也试 3 次失败，则报错
        6. 当前段成功后，下一段重新从 90 页开始尝试

        返回：
        ["page1_text", "page2_text", ...]
        """
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        print(f"[OCR] Total pages in source PDF: {total_pages}")

        all_page_texts: List[str] = []
        current_start_idx = 0  # 0-based
        batch_sizes = self._generate_batch_sizes()

        temp_dir = tempfile.mkdtemp(prefix="ocr_adaptive_")
        print(f"[OCR] Temp dir created: {temp_dir}")

        try:
            while current_start_idx < total_pages:
                remaining = total_pages - current_start_idx
                print(
                    f"[OCR] Starting new segment from page {current_start_idx + 1}, "
                    f"remaining pages: {remaining}"
                )

                segment_success = False
                last_error = None

                # 每一段都重新从最大页数开始试
                for batch_size in batch_sizes:
                    actual_size = min(batch_size, remaining)
                    start_idx = current_start_idx
                    end_idx = current_start_idx + actual_size - 1

                    if actual_size <= 0:
                        continue

                    split_pdf_path = self._write_pdf_range(
                        reader=reader,
                        start_idx=start_idx,
                        end_idx=end_idx,
                        temp_dir=temp_dir,
                    )

                    start_page = start_idx + 1
                    end_page = end_idx + 1
                    expected_count = actual_size

                    try:
                        page_texts = self._ocr_single_pdf_with_retries(
                            pdf_path=split_pdf_path,
                            batch_size=actual_size,
                            start_page=start_page,
                            end_page=end_page,
                        )

                        page_texts = self._normalize_page_texts(
                            page_texts=page_texts,
                            expected_count=expected_count,
                        )

                        all_page_texts.extend(page_texts)
                        current_start_idx += actual_size
                        segment_success = True

                        print(
                            f"[OCR] Segment success: pages {start_page}-{end_page}. "
                            f"Processed so far: {current_start_idx}/{total_pages}"
                        )
                        break

                    except Exception as e:
                        last_error = e
                        print(
                            f"[OCR] Batch size {actual_size} failed for pages "
                            f"{start_page}-{end_page}: {e}"
                        )
                        # 继续尝试更小批次

                if not segment_success:
                    raise RuntimeError(
                        f"OCR failed starting from page {current_start_idx + 1}. "
                        f"All batch sizes {batch_sizes} exhausted. Last error: {last_error}"
                    )

            print(f"[OCR] Total pages processed: {len(all_page_texts)}")
            return all_page_texts

        finally:
            # 清理临时目录
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"[OCR] Temp dir cleaned: {temp_dir}")
            except Exception as e:
                print(f"[OCR] Failed to clean temp dir {temp_dir}: {e}")