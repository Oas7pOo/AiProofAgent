# tools/proofread2_service.py
import os
import json
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .io_utils import load_json, save_json  # 你现有的通用 JSON IO :contentReference[oaicite:5]{index=5}
from .proofread_service import Terms, StageSpec, StageRunner  # 复用一校的术语模糊匹配与通用 runner


@dataclass
class Proof2Item:
    key: str
    page: Optional[int] = None
    block_num: Optional[int] = None
    en_block: str = ""
    zh_block: str = ""            # 原译（或原始译文）
    proofread1_zh: str = ""       # 一校译文
    proofread1_note: str = ""     # 一校建议
    proofread_zh: str = ""        # 二校译文（沿用字段名，便于复用 ExportManager 输出）
    proofread_note: str = ""      # 二校说明（沿用字段名）


def _filter_dataclass_kwargs(dc, raw: Dict[str, Any]) -> Dict[str, Any]:
    names = {f.name for f in fields(dc)}
    return {k: raw.get(k) for k in names if k in raw}


def _extract_terms_entries(t: Terms) -> List[Dict[str, str]]:
    """
    从 Terms.get_matchers() 提取可序列化的 term dict（en/zh/note），用于存档自包含。
    """
    entries: List[Dict[str, str]] = []
    seen = set()
    for _, term_dict in t.get_matchers():
        en = str(term_dict.get("en", "")).strip()
        if not en:
            continue
        key = en.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "en": en,
                "zh": str(term_dict.get("zh", "")).strip(),
                "note": str(term_dict.get("note", "")).strip(),
            }
        )
    return entries


def _build_terms_from_entries(entries: List[Dict[str, str]]) -> Terms:
    """
    从存档里的 entries 重建 Terms（不依赖外部术语文件）。
    注意：这里调用 Terms 的内部添加逻辑以获得与一校一致的 regex matcher 行为。
    """
    t = Terms()
    # Terms.import_* 会清理内部列表；这里我们手动重建
    t._entries = []
    t._matchers = []
    for e in entries or []:
        en = str(e.get("en", "")).strip()
        zh = str(e.get("zh", "")).strip()
        note = str(e.get("note", "")).strip()
        if en and zh:
            t._add_term(en, zh, note)
    return t


def find_latest_proof2_archive(archives_dir: str = "archives") -> Optional[str]:
    """
    自动搜索最近一次二校存档：
    1) 优先匹配 *_p2.json
    2) 兜底：扫描 .json 且 meta.stage == "proofread2"
    """
    if not os.path.isdir(archives_dir):
        return None

    # 1) 文件名约定优先
    cand = []
    for fn in os.listdir(archives_dir):
        if fn.lower().endswith("_p2.json"):
            cand.append(os.path.join(archives_dir, fn))
    if cand:
        cand.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return cand[0]

    # 2) 兜底：读取 meta.stage
    cand2 = []
    for fn in os.listdir(archives_dir):
        if not fn.lower().endswith(".json"):
            continue
        p = os.path.join(archives_dir, fn)
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("meta", {}).get("stage") == "proofread2":
                cand2.append(p)
        except Exception:
            continue
    if cand2:
        cand2.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return cand2[0]
    return None


class Proofread2Project:
    """
    二校项目：内存态 + 存档自包含（包含术语 entries）。
    """
    def __init__(self, archive_name: str):
        self.archive_name = archive_name
        self.items: List[Proof2Item] = []
        self.item_map: Dict[str, Proof2Item] = {}

        self.old_terms: Terms = Terms()
        self.new_terms: Optional[Terms] = None

        self.old_terms_entries: List[Dict[str, str]] = []
        self.new_terms_entries: List[Dict[str, str]] = []

        self.run_status: Dict[str, Any] = {}

    # ---------------- load/save ----------------

    def save_archive(self, out_path: str) -> None:
        data = {
            "meta": {
                "archive_name": self.archive_name,
                "stage": "proofread2",
            },
            "run_status": self.run_status,
            "terms": {
                "old_terms": self.old_terms_entries,
                "new_terms": self.new_terms_entries,
            },
            "items": [asdict(it) for it in self.items],
        }
        save_json(out_path, data)

    def load_archive(self, in_path: str) -> None:
        data = load_json(in_path)
        if not isinstance(data, dict):
            raise ValueError("二校存档 JSON 结构错误：必须是 dict。")

        meta = data.get("meta", {})
        self.archive_name = meta.get("archive_name", self.archive_name)

        self.run_status = data.get("run_status", {}) if isinstance(data.get("run_status"), dict) else {}

        terms = data.get("terms", {}) if isinstance(data.get("terms"), dict) else {}
        self.old_terms_entries = terms.get("old_terms", []) if isinstance(terms.get("old_terms"), list) else []
        self.new_terms_entries = terms.get("new_terms", []) if isinstance(terms.get("new_terms"), list) else []

        self.old_terms = _build_terms_from_entries(self.old_terms_entries)
        self.new_terms = _build_terms_from_entries(self.new_terms_entries) if self.new_terms_entries else None

        self.items = []
        self.item_map = {}
        for raw in data.get("items", []):
            if not isinstance(raw, dict):
                continue
            it = Proof2Item(**_filter_dataclass_kwargs(Proof2Item, raw))
            self.items.append(it)
            self.item_map[it.key] = it

    # ---------------- inputs (new project) ----------------

    def load_terms_old(self, path: str) -> None:
        t = Terms()
        if path.lower().endswith(".csv"):
            t.import_from_csv(path)
        elif path.lower().endswith(".json"):
            t.import_from_json(path)
        else:
            raise ValueError("旧术语表只支持 CSV/JSON。")

        self.old_terms = t
        self.old_terms_entries = _extract_terms_entries(t)

    def load_terms_new_optional(self, path: Optional[str]) -> None:
        if not path:
            self.new_terms = None
            self.new_terms_entries = []
            return

        t = Terms()
        if path.lower().endswith(".csv"):
            t.import_from_csv(path)
        elif path.lower().endswith(".json"):
            t.import_from_json(path)
        else:
            raise ValueError("新术语表只支持 CSV/JSON。")

        self.new_terms = t
        self.new_terms_entries = _extract_terms_entries(t)

    def import_from_stage1_any(self, stage1_path: str) -> None:
        """
        新建二校：读取一校结果（兼容三种）：
        1) 原始 json（list，每项包含 key/original/translation）：一校字段为空
        2) 一校新存档（dict + items，每项包含 en_block/zh_block/proofread_zh/proofread_note）
        3) 一校导出 json（list，每项包含 key/original/translation/proofread/suggestion）
        """
        data = load_json(stage1_path)
        if data is None:
            raise ValueError(f"无法读取一校文件: {stage1_path}")

        items: List[Proof2Item] = []

        # 2) 一校存档 dict
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            for raw in data["items"]:
                if not isinstance(raw, dict):
                    continue
                key = raw.get("key") or raw.get("BLOCK_ID")
                if not key:
                    continue
                en = raw.get("en_block") or raw.get("original") or ""
                zh = raw.get("zh_block") or raw.get("translation") or raw.get("original_translation") or ""
                p1 = raw.get("proofread_zh") or raw.get("proofread") or raw.get("proofread_translation") or ""
                n1 = raw.get("proofread_note") or raw.get("suggestion") or ""

                zh = str(zh or "").strip()
                p1 = str(p1 or "").strip()
                if (not zh) and p1:
                    zh = p1

                items.append(
                    Proof2Item(
                        key=str(key),
                        page=raw.get("page"),
                        block_num=raw.get("block_num"),
                        en_block=str(en),
                        zh_block=str(zh),
                        proofread1_zh=str(p1),
                        proofread1_note=str(n1),
                    )
                )

        # 1/3) list：原始 json 或 一校导出 json
        elif isinstance(data, list):
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                key = raw.get("key") or raw.get("BLOCK_ID")
                if not key:
                    continue
                en = raw.get("original") or raw.get("en_block") or ""
                zh = raw.get("translation") or raw.get("zh_block") or raw.get("original_translation") or ""

                # 一校导出 json
                p1 = raw.get("proofread") or raw.get("proofread_translation") or raw.get("proofread_zh") or ""
                n1 = raw.get("suggestion") or raw.get("proofread_note") or ""

                zh = str(zh or "").strip()
                p1 = str(p1 or "").strip()
                if (not zh) and p1:
                    zh = p1

                items.append(
                    Proof2Item(
                        key=str(key),
                        en_block=str(en),
                        zh_block=str(zh),
                        proofread1_zh=str(p1),
                        proofread1_note=str(n1),
                    )
                )
        else:
            raise ValueError("一校文件格式不支持：必须是 list 或 dict(items=...).")

        self.items = items
        self.item_map = {it.key: it for it in items}

    # ---------------- batching / terms match ----------------

    def pending_items(self) -> List[Proof2Item]:
        return [it for it in self.items if not (it.proofread_zh and it.proofread_zh.strip())]

    def build_batches(self, *, max_blocks: int, max_chars: int) -> List[List[Proof2Item]]:
        """
        同时按 max_blocks 与 max_chars 分包（max_chars 为近似字符预算）。
        """
        pend = self.pending_items()
        if not pend:
            return []

        batches: List[List[Proof2Item]] = []
        cur: List[Proof2Item] = []
        cur_chars = 0

        def _item_cost(x: Proof2Item) -> int:
            # 粗略估计：把会进入 prompt 的字段都算上
            return (
                len(x.en_block or "")
                + len(x.zh_block or "")
                + len(x.proofread1_zh or "")
                + len(x.proofread1_note or "")
                + 80
            )

        for it in pend:
            cost = _item_cost(it)
            if cur and (len(cur) >= max_blocks or (cur_chars + cost) > max_chars):
                batches.append(cur)
                cur = []
                cur_chars = 0
            cur.append(it)
            cur_chars += cost

        if cur:
            batches.append(cur)
        return batches

    def match_terms_for_batch(self, batch: List[Proof2Item]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """
        返回 (old_hits, new_hits)；默认旧术语优先：同 en 冲突时，新术语会被过滤掉。
        匹配逻辑与一校一致：对每个 term regex，在英文块上 search 命中即可 :contentReference[oaicite:7]{index=7}
        """
        old_map: Dict[str, Dict[str, str]] = {}
        new_map: Dict[str, Dict[str, str]] = {}

        old_matchers = self.old_terms.get_matchers() if self.old_terms else []
        new_matchers = self.new_terms.get_matchers() if self.new_terms else []

        for it in batch:
            text = it.en_block or ""
            for regex, term_dict in old_matchers:
                if regex.search(text):
                    old_map[term_dict["en"]] = term_dict
            for regex, term_dict in new_matchers:
                if regex.search(text):
                    new_map[term_dict["en"]] = term_dict

        # 旧优先：去掉与旧重复的 new
        for k in list(new_map.keys()):
            if k in old_map:
                new_map.pop(k, None)

        return list(old_map.values()), list(new_map.values())

    # ---------------- prompt / validation / apply ----------------

    def build_prompt(self, batch: List[Proof2Item], old_hits: List[Dict[str, str]], new_hits: List[Dict[str, str]]) -> str:
        def _fmt_terms(lst: List[Dict[str, str]]) -> str:
            if not lst:
                return "无"
            lines = []
            for t in lst:
                note = str(t.get("note", "")).strip()
                if note:
                    lines.append(f"- {t.get('en')}: {t.get('zh')}  # {note}")
                else:
                    lines.append(f"- {t.get('en')}: {t.get('zh')}")
            return "\n".join(lines)

        blocks = []
        for it in batch:
            blocks.append(
                f"--- BLOCK_ID: {it.key} ---\n"
                f"原文: {it.en_block}\n"
                f"原译: {it.zh_block}\n"
                f"一校译文: {it.proofread1_zh}\n"
                f"一校建议: {it.proofread1_note}\n"
            )

        return (
            "你是中文 D&D 译文二校员。你熟悉dnd的中文翻译与术语，基于当前翻译稿件与并不熟悉dnd的一校译文/建议做最终二校，确保术语一致、语义准确、中文自然。\n"
            "\n"
            "【术语约束】\n"
            "1) 旧术语表为最高优先级（若旧术语命中，必须使用旧术语的译名）。\n"
            "2) 新术语建议仅在旧术语未覆盖时可参考，其中可能有误。\n"
            "\n"
            "【旧术语命中】\n"
            f"{_fmt_terms(old_hits)}\n"
            "\n"
            "【新术语建议命中】\n"
            f"{_fmt_terms(new_hits)}\n"
            "\n"
            "【需要二校的块】\n"
            + "\n".join(blocks)
            + "\n"
            "【输出要求】\n"
            "必须输出一个纯 JSON 列表，不要包含 Markdown。\n"
            "每个对象必须包含：BLOCK_ID / proofread_zh / proofread_note。\n"
            "proofread_zh 必须给出“最终二校译文”（即使与一校相同也要完整输出）。\n"
            "proofread_note 写修改原因及文中出现的术语；可以留空字符串。\n"
            "\n"
            "[\n"
            "  {\"BLOCK_ID\":\"...\",\"proofread_zh\":\"...\",\"proofread_note\":\"\"}\n"
            "]\n"
        )

    def validate_results(self, batch: List[Proof2Item], parsed_list: List[Dict[str, Any]]) -> Tuple[bool, str]:
        if not isinstance(parsed_list, list) or not parsed_list:
            return False, "解析结果为空或不是列表。"

        needed = {it.key for it in batch}
        got = set()

        for obj in parsed_list:
            if not isinstance(obj, dict):
                return False, "列表中存在非对象条目。"
            bid = str(obj.get("BLOCK_ID", "")).strip()
            if not bid:
                return False, "存在缺失 BLOCK_ID 的条目。"
            got.add(bid)

            if bid in needed:
                zh = str(obj.get("proofread_zh", "")).strip()
                if not zh:
                    return False, f"{bid}: proofread_zh 为空。"
                if zh == "[BLOCK_ERROR]":
                    return False, f"{bid}: 返回了 [BLOCK_ERROR]，按规则需要停下等待人工修正。"

        missing = needed - got
        if missing:
            return False, f"缺失块输出: {sorted(list(missing))[:5]} ..."

        return True, ""

    def apply_results(self, parsed_list: List[Dict[str, Any]]) -> int:
        cnt = 0
        for obj in parsed_list:
            bid = str(obj.get("BLOCK_ID", "")).strip()
            it = self.item_map.get(bid)
            if not it:
                continue
            it.proofread_zh = str(obj.get("proofread_zh", "")).strip()
            it.proofread_note = str(obj.get("proofread_note", "")).strip()
            cnt += 1
        return cnt

    def is_completed(self) -> bool:
        rs = self.run_status if isinstance(self.run_status, dict) else {}
        if rs.get("proofread2_completed") is True:
            return True
        return len(self.pending_items()) == 0

    def mark_completed(self) -> None:
        if not isinstance(self.run_status, dict):
            self.run_status = {}
        self.run_status["proofread2_completed"] = True
        self.run_status["completed_at"] = datetime.now().isoformat(timespec="seconds")

    def run_batches_threaded(
        self,
        llm_client,
        save_path: str,
        *,
        max_workers: int = 1,
        max_blocks: Optional[int] = None,
        max_chars: Optional[int] = None,
        time_wait: Optional[int] = None,
    ) -> None:
        """
        通用 StageRunner 执行入口（默认可单线程；多线程时注意请求端并发限制）。
        - max_blocks/max_chars/time_wait 若不传，优先从 llm_client.config 读取。
        """
        if max_blocks is None:
            max_blocks = int(getattr(llm_client, "config", {}).get("max_blocks", 5))
        if max_chars is None:
            max_chars = int(getattr(llm_client, "config", {}).get("max_chars", 6000))
        if time_wait is None:
            time_wait = int(getattr(llm_client, "config", {}).get("time_wait", 0))

        spec = Proofread2Spec(self)
        runner = StageRunner(llm_client, spec)

        # 连通性测试（最小批）
        if self.items:
            _ = runner.process_recursive([self.items[0]])

        batches = self.build_batches(max_blocks=max_blocks, max_chars=max_chars)
        if not batches:
            self.mark_completed()
            self.save_archive(save_path)
            return

        def _worker(batch: List[Proof2Item]) -> List[Dict[str, Any]]:
            res = runner.process_recursive(batch)
            time.sleep(time_wait)
            return res

        processed = 0
        consecutive_failures = 0
        MAX_FAILURES = 5

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {executor.submit(_worker, b): i for i, b in enumerate(batches)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    parsed = future.result()
                    spec.apply(batches[idx], parsed)
                    processed += 1
                    consecutive_failures = 0
                except Exception as e:
                    consecutive_failures += 1
                    print(f"[WARN] Batch {idx+1}/{len(batches)} failed: {e}")
                    if consecutive_failures >= MAX_FAILURES:
                        raise RuntimeError(f"Stopped: {MAX_FAILURES} consecutive batches failed.")
                finally:
                    self.save_archive(save_path)

        self.mark_completed()
        self.save_archive(save_path)



class Proofread2Spec(StageSpec):
    """二校规范：不输出 new_terms；只回填 proofread_zh / proofread_note。"""

    name = "proofread2"

    def __init__(self, project: Proofread2Project):
        self.project = project

    def build_context(self, batch_items: List[Proof2Item]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        return self.project.match_terms_for_batch(batch_items)

    def build_prompt(self, batch_items: List[Proof2Item], context: Tuple[List[Dict[str, str]], List[Dict[str, str]]]) -> str:
        old_hits, new_hits = context
        return self.project.build_prompt(batch_items, old_hits=old_hits, new_hits=new_hits)

    def validate(self, batch_items: List[Proof2Item], parsed_list: List[Dict[str, Any]]) -> None:
        # 先走通用检查
        super().validate(batch_items, parsed_list)
        ok, msg = self.project.validate_results(batch_items, parsed_list)
        if not ok:
            raise ValueError(msg)

    def fill_missing(self, missing_ids: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "BLOCK_ID": mid,
                "proofread_zh": "[AI_DROP]",
                "proofread_note": "[SYSTEM] AI response dropped this block.",
            }
            for mid in missing_ids
        ]

    def fail_item(self, item_id: str, reason: str) -> Dict[str, Any]:
        return {
            "BLOCK_ID": item_id,
            "proofread_zh": "[AI_ERROR]",
            "proofread_note": f"[SYSTEM] {reason}",
        }

    def apply(self, batch_items: List[Proof2Item], parsed_list: List[Dict[str, Any]]) -> int:
        # project.apply_results 会基于 item_map 回填
        return self.project.apply_results(parsed_list)
