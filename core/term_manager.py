import json
import csv
import logging
import re
from typing import List, Tuple, Any
from models.term import TermEntry

logger = logging.getLogger("AiProofAgent.TermManager")

class TermManager:
    """
    负责管理术语表 (CSV/JSON)，从中解析为统一的 TermEntry 集合，
    用作 LLM Prompt 的外部词汇注入依赖。
    """
    def __init__(self):
        self.terms: List[TermEntry] = []
        self._matchers: List[Tuple[Any, TermEntry]] = []
        
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

    def load_terms(self, file_path: str):
        if not file_path:
            return
        try:
            if file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        self.terms.append(TermEntry(
                            term=item.get("en", ""),
                            translation=item.get("zh", ""),
                            note=item.get("note", "")
                        ))
            elif file_path.endswith('.csv'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.terms.append(TermEntry(
                            term=row.get("en", ""),
                            translation=row.get("zh", ""),
                            note=row.get("note", "")
                        ))
            self._build_matchers()
            logger.info(f"成功加载术语表: {file_path}，共 {len(self.terms)} 条记录")
        except Exception as e:
            logger.error(f"加载术语表失败: {e}", exc_info=True)
            raise

    def _build_matchers(self):
        self._matchers = []
        for entry in self.terms:
            en = entry.term.strip()
            if not en or not re.search(r'[a-zA-Z]', en):
                continue
            try:
                # 不管术语长短，都使用 OCR 混淆字符映射进行模糊匹配
                core_chars = re.sub(r'[\s\W_]+', '', en)
                regex_parts = [self.ocr_map.get(c.lower(), re.escape(c)) for c in core_chars]
                pattern = r"[\s\W_]*".join(regex_parts)
                self._matchers.append((re.compile(pattern, re.IGNORECASE), entry))
            except Exception as e:
                logger.warning(f"构建正则失败 '{en}': {e}")
                
    def match_terms(self, text: str) -> List[TermEntry]:
        """通过正则容错在文本中匹配出存在的术语"""
        if not text: return []
        hits = {}
        for regex, entry in self._matchers:
            if regex.search(text):
                hits[entry.term] = entry
        return list(hits.values())
