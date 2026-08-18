# core/term_manager.py
import json
import csv
import logging
import re

# 新增：需要 pip install regex
import regex

from typing import List, Tuple, Any
from models.term import TermEntry

logger = logging.getLogger("AiProofAgent.TermManager")


class TermManager:
    def __init__(self, fuzzy_edit_distance: int = 1):
        self.terms: List[TermEntry] = []
        self._matchers: List[Tuple[Any, TermEntry]] = []
        self._fuzzy_matchers: List[Tuple[Any, TermEntry]] = []
        self.fuzzy_edit_distance = fuzzy_edit_distance
        self.ocr_map = {
            'l': '[lLiI1|!]',
            'i': '[lLiI1|!]',
            '1': '[lLiI1|!]',
            'o': '[oO0QD]',
            '0': '[oO0QD]'
        }

    def load_terms(self, file_path: str):
        if not file_path:
            return
        try:
            items = []
            if file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    items = json.load(f)
            elif file_path.endswith('.csv'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    items = list(csv.DictReader(f))

            for item in items:
                term_val = (item.get("term") or item.get("en") or "").strip()
                trans_val = (item.get("translation") or item.get("zh") or "").strip()
                note_val = (item.get("note") or "").strip()

                if term_val and re.search(r'[a-zA-Z]', term_val):
                    self.terms.append(
                        TermEntry(term=term_val, translation=trans_val, note=note_val)
                    )

            self._build_matchers()
            logger.info(f"成功加载术语: {len(self.terms)} 条来自 {file_path}")
        except Exception as e:
            logger.error(f"加载失败: {e}")

    def _build_matchers(self):
        self._matchers = []
        self._fuzzy_matchers = []

        for entry in self.terms:
            en = entry.term
            if not en or not re.search(r'[a-zA-Z0-9]', en):
                continue

            # ---------- 1. 原有精确 OCR 匹配 ----------
            regex_parts = [
                self.ocr_map.get(c.lower(), re.escape(c))
                for c in en
                if not c.isspace()
            ]
            exact_pattern = r"\s*".join(regex_parts)
            self._matchers.append(
                (re.compile(r'\b' + exact_pattern + r'\b', re.IGNORECASE), entry)
            )

            # ---------- 2. 新增模糊匹配 ----------
            # 去掉空格，生成紧凑小写形式，如 "Send Dreams" -> "senddreams"
            compact = ''.join(c for c in en if not c.isspace()).lower()

            # 太短的术语模糊匹配容易误报，可以设置一个阈值
            if len(compact) < 4:
                continue

            fuzzy_parts = [
                self.ocr_map.get(c, regex.escape(c))
                for c in compact
            ]

            # 每个字符之间允许任意空白，例如：
            # senddreams -> s\s*e\s*n\s*d\s*d\s*r\s*e\s*a\s*m\s*s
            fuzzy_pattern = r'\s*'.join(fuzzy_parts)

            # 允许最多 fuzzy_edit_distance 个插入/删除/替换错误
            # {e<=1} 表示编辑距离 <= 1
            max_err = self.fuzzy_edit_distance
            pattern = (
                r'\b(?:' + fuzzy_pattern + r'){e<=' + str(max_err) + r'}\b'
            )

            # BESTMATCH 会尽量找最佳匹配，但会稍慢；如果性能敏感可以去掉
            self._fuzzy_matchers.append(
                (
                    regex.compile(
                        pattern,
                        regex.IGNORECASE | regex.BESTMATCH
                    ),
                    entry
                )
            )

    def match_terms(self, text: str) -> List[TermEntry]:
        if not text:
            return []

        hits = {}

        # 先精确匹配，确保准确率
        for regex_obj, entry in self._matchers:
            if regex_obj.search(text):
                hits[entry.term] = entry

        # 再模糊匹配，补充未命中的术语
        for regex_obj, entry in self._fuzzy_matchers:
            if entry.term not in hits and regex_obj.search(text):
                hits[entry.term] = entry

        return list(hits.values())