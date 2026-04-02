# core/term_manager.py 完整修复版
import json, csv, logging, re
from typing import List, Tuple, Any
from models.term import TermEntry

logger = logging.getLogger("AiProofAgent.TermManager")

class TermManager:
    def __init__(self):
        self.terms: List[TermEntry] = []
        self._matchers: List[Tuple[Any, TermEntry]] = []
        self.ocr_map = {'l': '[lLiI1|!]', 'i': '[lLiI1|!]', '1': '[lLiI1|!]', 'o': '[oO0QD]', '0': '[oO0QD]'}

    def load_terms(self, file_path: str):
        if not file_path: return
        try:
            items = []
            if file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    items = json.load(f)
            elif file_path.endswith('.csv'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    items = list(csv.DictReader(f))

            for item in items:
                # 核心修复：兼容多种键名并去除空格
                term_val = (item.get("term") or item.get("en") or "").strip()
                trans_val = (item.get("translation") or item.get("zh") or "").strip()
                note_val = (item.get("note") or "").strip()
                
                # 过滤掉不包含英文或数字的术语
                if term_val and re.search(r'[a-zA-Z]', term_val):
                    self.terms.append(TermEntry(term=term_val, translation=trans_val, note=note_val))
            
            self._build_matchers()
            logger.info(f"成功加载术语: {len(self.terms)} 条来自 {file_path}")
        except Exception as e:
            logger.error(f"加载失败: {e}")

    def _build_matchers(self):
        self._matchers = []
        for entry in self.terms:
            en = entry.term
            if not en or not re.search(r'[a-zA-Z0-9]', en): continue
            try:
                # 改进正则：允许术语内部有任意空白
                regex_parts = [self.ocr_map.get(c.lower(), re.escape(c)) for c in en if not c.isspace()]
                pattern = r"\s*".join(regex_parts)
                # 加上单词边界，防止误伤（如 'Crypt' 匹配到 'Cryptography'）
                self._matchers.append((re.compile(r'\b' + pattern + r'\b', re.IGNORECASE), entry))
            except: continue

    def match_terms(self, text: str) -> List[TermEntry]:
        if not text: return []
        hits = {}
        for regex, entry in self._matchers:
            if regex.search(text):
                hits[entry.term] = entry
        return list(hits.values())