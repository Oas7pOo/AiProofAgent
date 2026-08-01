from typing import List

from models.document import TranslationBlock
from models.term import TermEntry


def match_terms_for_block(
    block: TranslationBlock,
    old_terms,
    new_terms,
) -> tuple:
    """为单个块匹配术语，返回 (old_hits, new_hits)。"""
    block_old_hits = old_terms.match_terms(block.en_block)
    block_new_hits = new_terms.match_terms(block.en_block)
    block_old_terms = {term.term for term in block_old_hits}
    block_new_hits = [
        term
        for term in block_new_hits
        if term.term not in block_old_terms
    ]
    return block_old_hits, block_new_hits


def format_terms(terms: List[TermEntry]) -> str:
    """将术语列表格式化为字符串。"""
    if not terms:
        return "无"

    seen = set()
    lines = []
    for term in terms:
        source = str(term.term).strip()
        if not source or source in seen:
            continue

        translation = str(term.translation).strip()
        note = f" ({term.note})" if term.note else ""
        lines.append(f"- {source}: {translation}{note}")
        seen.add(source)

    return "\n".join(lines)
