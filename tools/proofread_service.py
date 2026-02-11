import json
import re
import time
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# [关键] 引入公用 IO 组件
from .io_utils import read_csv_schema, load_json, save_json

# ==================== 数据结构层 ====================

@dataclass
class AlignItem:
    key: str
    page: Optional[int]
    block_num: Optional[int]
    en_block: str
    zh_block: str
    proofread_zh: str = ""
    proofread_note: str = ""
    # [修复] 找回被我弄丢的字段和初始化逻辑
    new_terms: List[Dict[str, str]] = None 

    def __post_init__(self):
        # 确保默认值是空列表而不是 None (为了序列化方便)
        if self.new_terms is None:
            self.new_terms = []

@dataclass
class TermEntry:
    en: str
    zh: str
    note: str = ""

# ==================== 业务逻辑层 ====================

class Terms:
    def __init__(self):
        self._entries: List[TermEntry] = []
        self._matchers: List[Tuple[Any, Dict]] = []
        
        # 定义 OCR 混淆字符 (字符 -> 正则集合)
        self.ocr_map = {
            'l': '[lLiI1|!]', 'i': '[lLiI1|!]', '1': '[lLiI1|!]',
            'o': '[oO0QD]',   '0': '[oO0QD]',
            's': '[sS5$]',    '5': '[sS5$]',
            'a': '[aA4@]',    'e': '[eE3]',
            't': '[tT7]',     'b': '[bB8]',
            'g': '[gG69]',    'z': '[zZ2]',
            'c': '[cC(]',     '(': '[cC(]'
        }

    def __len__(self):
        return len(self._entries)

    def get_matchers(self):
        return self._matchers

    def _add_term(self, en: str, zh: str, note: str) -> bool:
        en = str(en).strip()
        zh = str(zh).strip()

        # 过滤无效术语
        if not re.search(r'[a-zA-Z]', en):
            return False

        entry = TermEntry(en, zh, note)
        self._entries.append(entry)

        try:
            pattern = ""
            clean_en = en.strip()
            if len(clean_en) <= 4:
                # 短词
                pattern = r'\b' + re.escape(clean_en) + r'\b'
            else:
                # 长词 (OCR 模糊)
                core_chars = re.sub(r'[\s\W_]+', '', clean_en)
                regex_parts = []
                for char in core_chars:
                    c_lower = char.lower()
                    char_pattern = self.ocr_map.get(c_lower, re.escape(char))
                    regex_parts.append(char_pattern)
                pattern = r"[\s\W_]*".join(regex_parts)

            compiled_re = re.compile(pattern, re.IGNORECASE)
            self._matchers.append((compiled_re, asdict(entry)))
            return True

        except Exception as e:
            print(f"[WARN] Regex Error for '{en}': {e}")
            return False

    def import_from_csv(self, csv_path: str) -> None:
        try:
            df = read_csv_schema(
                csv_path,
                schema=["en", "zh", "note"],  # 第3列当备注/词性/说明
                drop_first_row="auto",
                treat_first_row_as_header="auto",
                strict=False,  # 术语表可以稍微宽松点
            )

            self._entries = []
            self._matchers = []
            count_valid = 0

            for _, row in df.iterrows():
                en = str(row.get("en", "")).strip()
                zh = str(row.get("zh", "")).strip()
                note = str(row.get("note", "")).strip()
                if self._add_term(en, zh, note):
                    count_valid += 1

            print(f"[INFO] CSV Terms loaded: {count_valid}")

        except Exception as e:
            print(f"[ERROR] CSV Terms load failed: {e}")

    def import_from_json(self, file_path: str) -> None:
        try:
            # [关键] 调用 io_utils
            data = load_json(file_path)
            if isinstance(data, dict): data = [data]
            
            self._entries = []
            self._matchers = []
            count_valid = 0

            for item in data:
                en = item.get("term", "")
                zh = item.get("translation", "")
                note = item.get("note", "")
                if self._add_term(en, zh, note):
                    count_valid += 1
            
            print(f"[INFO] JSON Terms loaded: {count_valid}")

        except Exception as e:
            print(f"[ERROR] JSON Load failed: {e}")

class ProofreadProject:
    def __init__(self, archive_name: str, job_count: int = 1):
        self.archive_name = archive_name
        self.job_count = job_count
        self.items: List[AlignItem] = []

class StageSpec:
    """阶段规范：承载 prompt/schema/校验/回填等差异。"""

    name: str = ""

    def build_context(self, batch_items: List[Any]) -> Any:
        return None

    def build_prompt(self, batch_items: List[Any], context: Any) -> str:
        raise NotImplementedError

    def validate(self, batch_items: List[Any], parsed_list: List[Dict[str, Any]]) -> None:
        # 允许实现自行加严；默认只检查“是 list 且每项是 dict 且有 BLOCK_ID”
        if not isinstance(parsed_list, list) or not parsed_list:
            raise ValueError("解析结果为空或不是列表。")
        for obj in parsed_list:
            if not isinstance(obj, dict):
                raise ValueError("列表中存在非对象条目。")
            bid = str(obj.get("BLOCK_ID", "")).strip()
            if not bid:
                raise ValueError("存在缺失 BLOCK_ID 的条目。")

    def get_input_ids(self, batch_items: List[Any]) -> List[str]:
        ids = []
        for it in batch_items:
            if isinstance(it, dict):
                ids.append(str(it.get("key", "")).strip())
            else:
                ids.append(str(getattr(it, "key", "")).strip())
        return [x for x in ids if x]

    def get_returned_ids(self, parsed_list: List[Dict[str, Any]]) -> set:
        return {str(r.get("BLOCK_ID", "")).strip() for r in parsed_list if isinstance(r, dict)}

    def fill_missing(self, missing_ids: List[str]) -> List[Dict[str, Any]]:
        return []

    def fail_item(self, item_id: str, reason: str) -> Dict[str, Any]:
        raise NotImplementedError

    def apply(self, batch_items: List[Any], parsed_list: List[Dict[str, Any]]) -> int:
        raise NotImplementedError


class StageRunner:
    """通用流水线：重试/拆分/补齐，不认识任何业务字段。"""

    def __init__(self, llm_client, spec: StageSpec):
        self.llm = llm_client
        self.spec = spec

    def process_recursive(self, batch_items: List[Any], depth: int = 0) -> List[Dict[str, Any]]:
        MAX_RETRIES = 3

        for attempt in range(MAX_RETRIES):
            try:
                ctx = self.spec.build_context(batch_items)
                prompt = self.spec.build_prompt(batch_items, ctx)
                results = self.llm.request_prompt(prompt)

                if not isinstance(results, list):
                    raise ValueError("解析结果不是列表。")

                # 自动补齐缺失块，避免不必要的拆分
                input_ids = self.spec.get_input_ids(batch_items)
                returned_ids = self.spec.get_returned_ids(results)
                missing_ids = [kid for kid in input_ids if kid not in returned_ids]
                if missing_ids:
                    print(f"  [WARN] Batch incomplete ({len(results)}/{len(batch_items)}). Auto-filling {len(missing_ids)} missing blocks.")
                    results.extend(self.spec.fill_missing(missing_ids))

                # 阶段校验（可加严）
                self.spec.validate(batch_items, results)
                return results

            except Exception as e:
                # 致命错误直接熔断
                if any(x in str(e) for x in ["HTTP 401", "HTTP 403", "insufficient_quota"]):
                    raise

                if attempt < MAX_RETRIES - 1:
                    if depth > 0:
                        print(f"  [Depth={depth}] Retry {attempt+1}/{MAX_RETRIES}: {e}")
                    time.sleep(2)
                else:
                    print(f"  [Depth={depth}] All retries failed: {e}")

        # 拆分阶段：只有当重试彻底失败才会走到这里
        if len(batch_items) > 1:
            mid = len(batch_items) // 2
            left, right = batch_items[:mid], batch_items[mid:]
            return self.process_recursive(left, depth + 1) + self.process_recursive(right, depth + 1)

        # 单条失败：返回阶段定义的失败标记
        item_id = self.spec.get_input_ids(batch_items)[0] if batch_items else "unknown"
        print(f"[Depth={depth}] Item failed. Tagging as [AI_ERROR]: {item_id}")
        return [self.spec.fail_item(item_id, "Processing failed after max retries.")]


class Proofread1Spec(StageSpec):
    """一校规范：输出包含 new_terms。"""

    name = "proofread1"

    def __init__(self, terms: Terms):
        self.terms = terms

    def build_context(self, batch_items: List[AlignItem]) -> List[Dict[str, str]]:
        batch_terms_map: Dict[str, Dict[str, str]] = {}
        matchers = self.terms.get_matchers()

        for item in batch_items:
            text = item.en_block or ""
            for regex, term_dict in matchers:
                if regex.search(text):
                    batch_terms_map[term_dict["en"]] = term_dict

        return list(batch_terms_map.values())

    def _format_terms(self, terms: List[Dict[str, str]]) -> str:
        if not terms:
            return "无"
        # 去重 + 保序
        seen = set()
        out_lines = []
        for t in terms:
            key = str(t.get("en", "")).strip()
            if not key or key in seen:
                continue
            zh = str(t.get("zh", "")).strip()
            out_lines.append(f"- {key}: {zh}")
            seen.add(key)
        return "\n".join(out_lines)

    def build_prompt(self, batch_items: List[AlignItem], context: List[Dict[str, str]]) -> str:
        terms_str = self._format_terms(context)

        blocks_text = []
        for item in batch_items:
            blocks_text.append(
                f"--- BLOCK_ID: {item.key} ---\n"
                f"原文: {item.en_block}\n"
                f"原译文: {item.zh_block}\n"
            )
        content_str = "\n".join(blocks_text)

        return f"""
【角色设定】
你是一个严谨的本地化校对专家。你的任务是根据参考术语校对原文和译文。

【待处理内容】
{content_str}

【参考术语】
{terms_str}

【处理逻辑 - 请严格遵守】
对于每一个 Block，请先判断其是否可以正常处理，并从以下两种模式中选择一种输出：

模式 A：正常校对（绝大多数情况）
- 适用场景：原文可读，且你能提供有效的校对建议。
- proofread_zh：输出修正后的译文。
- proofread_note：输出具体的修改原因（如：术语修正/语法优化/风格调整）。请不要写“无”、“没问题”，如果没有修改，请留空字符串。
- new_terms: 仅当该块中出现明确“专有名词/术语/人名/地名”且不在术语表内时才输出；否则 []。
  new_terms 每项必须是：{{"term": "英文术语", "translation": "中文译名", "note": "可选备注"}}

模式 B：异常报错（极少数情况）
- 适用场景：原文全是乱码、原文不仅是外语还是无法理解的字符、或者内容违反安全策略。
- proofread_zh：必须输出固定标签 "[BLOCK_ERROR]"。
- proofread_note：必须说明无法处理的具体技术原因（如：GARBLED_TEXT, SAFETY_FILTER）。

【输出格式】
必须输出一个纯 JSON 列表，不要包含 Markdown 标记。
[
  {{
    "BLOCK_ID": "保持原样",
    "proofread_zh": "修正后的译文 或 [BLOCK_ERROR]",
    "proofread_note": "语言学备注 或 错误原因",
    "new_terms": []
  }}
]
"""

    def fill_missing(self, missing_ids: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "BLOCK_ID": mid,
                "proofread_zh": "[AI_DROP]",
                "proofread_note": "[SYSTEM] AI response dropped this block.",
                "new_terms": [],
            }
            for mid in missing_ids
        ]

    def fail_item(self, item_id: str, reason: str) -> Dict[str, Any]:
        return {
            "BLOCK_ID": item_id,
            "proofread_zh": "[AI_ERROR]",
            "proofread_note": f"[SYSTEM] {reason}",
            "new_terms": [],
        }

    def apply(self, batch_items: List[AlignItem], parsed_list: List[Dict[str, Any]]) -> int:
        batch_map = {it.key: it for it in batch_items}
        count = 0
        for res in parsed_list:
            if not isinstance(res, dict):
                continue
            block_id = str(res.get("BLOCK_ID", "")).strip()
            item = batch_map.get(block_id)
            if not item:
                continue

            item.proofread_zh = str(res.get("proofread_zh", "") or "")
            item.proofread_note = str(res.get("proofread_note", "") or "")

            raw_new_terms = res.get("new_terms", [])
            if isinstance(raw_new_terms, list):
                item.new_terms = raw_new_terms
            else:
                item.new_terms = []

            count += 1
        return count

class ProofreadApp:
    def __init__(self, archive_name: str, config: dict = None, job_count: int = 1):
        # 移除了 self.csv 和 self.jsonrw，直接用 io_utils
        self.project = ProofreadProject(archive_name, job_count)
        self.terms = Terms()
        self._key_pat = re.compile(r".*(\d+).*?(\d+).*")
        
        # OCR Config Injection
        self.ocr_config = config.get('ocr') if config else None

    def load_terms(self, file_path: str):
        if not os.path.exists(file_path):
            print(f"[WARN] Term file not found: {file_path}")
            return

        if file_path.lower().endswith('.json'):
            print(f"[INFO] Loading JSON terms from {file_path}")
            self.terms.import_from_json(file_path)
        elif file_path.lower().endswith('.csv'):
            print(f"[INFO] Loading CSV terms from {file_path}")
            self.terms.import_from_csv(file_path)
        else:
            print("[ERROR] Unsupported term file format. Use .csv or .json")

        print(f"[INFO] Total Terms loaded: {len(self.terms)}")

    def _parse_key_meta(self, key_str: str) -> Tuple[int, int]:
        m = self._key_pat.search(key_str or "")
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    def import_from_csv(self, csv_path: str) -> None:
        try:
            df = read_csv_schema(
                csv_path,
                schema=["key", "en", "zh"],
                drop_first_row="auto",
                treat_first_row_as_header="auto",
                strict=True,
            )

            self.project.items = []
            for _, row in df.iterrows():
                key = str(row["key"]).strip()
                page, block_num = self._parse_key_meta(key)
                self.project.items.append(AlignItem(
                    key=key,
                    page=page,
                    block_num=block_num,
                    en_block=str(row["en"]),
                    zh_block=str(row["zh"]),
                ))
        except Exception as e:
            print(f"[ERROR] Import CSV failed: {e}")

    def import_from_json(self, json_path: str) -> None:
        """从原始 JSON 文件导入数据 (List[Dict])"""
        raw_data = load_json(json_path)
        if not raw_data or not isinstance(raw_data, list):
            print(f"[ERROR] Invalid source JSON: {json_path}. Must be a list.")
            return

        self.project.items = []
        for entry in raw_data:
            key = entry.get("key")
            page, block_num = self._parse_key_meta(key)
            self.project.items.append(AlignItem(
                key=key,
                page=page,
                block_num=block_num,
                en_block=entry.get("original", ""),
                zh_block=entry.get("translation", "")
            ))
        
        print(f"[INFO] Imported {len(self.project.items)} items from JSON source.")

    def import_from_pdf(self, pdf_path: str) -> None:
        """集成 PDF 导入"""
        if not self.ocr_config:
            print("[ERROR] Cannot import PDF: OCR config missing.")
            return
        
        # 这是一个循环依赖的痛点，但为了简单，我们在方法内导入 DataConverter
        from .data_converter import DataConverter
        
        # 使用当前配置创建一个 Converter
        temp_cfg = {'ocr': self.ocr_config}
        converter = DataConverter(temp_cfg)
        
        # 临时文件
        temp_json = pdf_path + ".temp.json"
        try:
            converter.pdf_to_file(pdf_path, temp_json, 'json')
            self.import_from_json(temp_json)
        finally:
            if os.path.exists(temp_json):
                os.remove(temp_json)

    def export_project_json(self, out_path: str) -> None:
        data = {
            "meta": {"archive_name": self.project.archive_name, "job_count": self.project.job_count},
            "items": [asdict(it) for it in self.project.items],
        }
        save_json(out_path, data)

    def load_project_json(self, in_path: str) -> None:
        data = load_json(in_path)
        if not data: return
        meta = data.get("meta", {})
        self.project.archive_name = meta.get("archive_name", self.project.archive_name)
        self.project.job_count = int(meta.get("job_count", self.project.job_count))
        self.project.items = []
        for raw in data.get("items", []):
            self.project.items.append(AlignItem(**raw))
        print(f"[INFO] Project loaded: {len(self.project.items)} items")

    # ================= 内部辅助方法 (Private Helpers) =================

    def _check_connectivity(self, runner: StageRunner) -> None:
        """执行 AI 连通性测试（走当前阶段 spec 的 prompt/schema）。"""
        print("\n[INFO] Checking AI connectivity...")
        try:
            if self.project.items:
                test_item = self.project.items[0]
            else:
                test_item = AlignItem(key="TEST", page=None, block_num=None, en_block="Hi", zh_block="嗨")

            results = runner.process_recursive([test_item])
            if not results:
                raise ValueError("Test request returned empty result.")
            print("[OK] AI Check Passed.")
        except Exception as e:
            raise RuntimeError(f"AI Connection Failed: {e}")

    def _prepare_batches(self, batch_size: int) -> List[List[AlignItem]]:
        """筛选待处理项并分包"""
        pending = [it for it in self.project.items if not (it.proofread_zh and it.proofread_zh.strip())]
        if not pending:
            return []

        batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
        print(f"[INFO] Pending: {len(pending)} items | Batches: {len(batches)}")
        return batches

    def _execute_batch_task(self, batch_idx: int, batch_data: List[AlignItem], runner: StageRunner, time_wait: int):
        """线程池 Worker：只负责调用 runner 获取结果，不做任何阶段逻辑。"""
        results = runner.process_recursive(batch_data)
        time.sleep(time_wait)
        return batch_idx, results

    def _run_execution_loop(
        self,
        batches: List[List[AlignItem]],
        runner: StageRunner,
        spec: StageSpec,
        max_workers: int,
        time_wait: int,
        save_path: str,
    ) -> None:
        """核心执行循环"""
        processed_batches = 0
        consecutive_failures = 0
        MAX_FAILURES = 5

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(self._execute_batch_task, idx, batch, runner, time_wait): idx
                for idx, batch in enumerate(batches)
            }

            try:
                for future in as_completed(future_to_batch):
                    batch_idx = future_to_batch[future]
                    _, results = future.result()

                    if results:
                        consecutive_failures = 0
                        count = spec.apply(batches[batch_idx], results)
                        print(f"  [Batch {batch_idx+1}/{len(batches)}] Done. Updated {count} items.")
                        processed_batches += 1
                    else:
                        consecutive_failures += 1
                        print(f"  [Batch {batch_idx+1}] Failed (Empty result).")
                        print(f"  [WARN] Consecutive failures: {consecutive_failures}/{MAX_FAILURES}")

                    if consecutive_failures >= MAX_FAILURES:
                        raise RuntimeError(f"Stopped: {MAX_FAILURES} consecutive batches failed.")

                    # 每完成一个 batch 就落盘一次（保证可恢复）
                    if processed_batches % 1 == 0:
                        self.export_project_json(save_path)

            except Exception as e:
                print(f"[FATAL] Execution interrupted: {e}")
                executor.shutdown(wait=False, cancel_futures=True)
                raise

    # ================= 主入口方法 (Main Entry) =================

    def run_alignment_batch_threaded(self, ai_service, save_path: str, max_workers: int = 1):
        """一校：使用 Proofread1Spec 生成 prompt/schema，并通过 StageRunner 执行。"""
        batch_size = ai_service.config.get("max_blocks")
        time_wait = ai_service.config.get("time_wait")

        if not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError(f"Invalid max_blocks: {batch_size}")
        if time_wait is None:
            time_wait = 0

        spec = Proofread1Spec(self.terms)
        runner = StageRunner(ai_service, spec)

        self._check_connectivity(runner)

        self.project.job_count += 1
        print(f"[INFO] Start Job #{self.project.job_count} | Workers: {max_workers} | Batch Size: {batch_size}")

        batches = self._prepare_batches(batch_size)
        if not batches:
            print("[INFO] All items completed.")
            return

        self._run_execution_loop(batches, runner, spec, max_workers, int(time_wait), save_path)

        self.export_project_json(save_path)
        print("[INFO] All tasks finished.")
