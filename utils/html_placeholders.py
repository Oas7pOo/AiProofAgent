"""保护 LLM 译文中的 HTML 标签，避免模型改写文档结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


class HtmlPlaceholderError(ValueError):
    """HTML 占位符缺失、重复或顺序被改写。"""


def _find_html_tag_spans(text: str) -> Iterable[Tuple[int, int]]:
    """返回 HTML 标签的字符区间，同时保留标签原始文本。"""
    index = 0

    while index < len(text):
        start = text.find("<", index)
        if start < 0 or start + 1 >= len(text):
            return

        next_char = text[start + 1]
        if not (next_char.isalpha() or next_char in {"/", "!", "?"}):
            index = start + 1
            continue

        cursor = start + 1
        quote = ""

        while cursor < len(text):
            char = text[cursor]
            if quote:
                if char == quote:
                    quote = ""
            elif char in {"'", '"'}:
                quote = char
            elif char == ">":
                yield start, cursor + 1
                index = cursor + 1
                break
            cursor += 1
        else:
            index = start + 1


@dataclass(frozen=True)
class HtmlPlaceholderCodec:
    """将 HTML 标签替换成不可翻译的占位符，并在响应后无损恢复。"""

    tags: Tuple[str, ...]

    @property
    def tokens(self) -> List[str]:
        return [
            f"[[HTML_TAG_{index:04d}]]"
            for index in range(1, len(self.tags) + 1)
        ]

    def protect(self, text: str) -> str:
        """用固定占位符替换文本中的 HTML 标签。"""
        result = text
        for token, tag in zip(self.tokens, self.tags):
            result = result.replace(tag, token, 1)
        return result

    def restore(self, text: str) -> str:
        """确认占位符完整有序后，将其还原成原始标签。"""
        found_tokens = []
        index = 0
        while True:
            start = text.find("[[HTML_TAG_", index)
            if start < 0:
                break
            end = text.find("]]", start + len("[[HTML_TAG_"))
            if end < 0:
                raise HtmlPlaceholderError("HTML 占位符未闭合")
            found_tokens.append(text[start:end + 2])
            index = end + 2

        if found_tokens != self.tokens:
            raise HtmlPlaceholderError(
                "HTML 标签占位符缺失、重复或顺序错误"
            )

        restored = text
        for token, tag in zip(self.tokens, self.tags):
            restored = restored.replace(token, tag, 1)
        return restored


@dataclass
class BatchPromptContext:
    """批次内稳定短 ID 与 HTML 标签保护状态。"""

    block_by_alias: Dict[str, Any]
    source_by_alias: Dict[str, str]
    html_codec_by_alias: Dict[str, HtmlPlaceholderCodec]

    @property
    def aliases(self) -> List[str]:
        return list(self.block_by_alias)

    def restore_response_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        restored_rows = []
        for row in rows:
            restored = dict(row)
            alias = str(restored["BLOCK_ID"])
            codec = self.html_codec_by_alias.get(alias)
            if codec:
                proofread_zh = restored.get("proofread_zh", "")
                if not isinstance(proofread_zh, str):
                    raise HtmlPlaceholderError(
                        f"{alias}.proofread_zh 不是字符串"
                    )
                restored["proofread_zh"] = codec.restore(proofread_zh)
            restored_rows.append(restored)
        return restored_rows


def build_batch_prompt_context(blocks: Iterable[Any]) -> BatchPromptContext:
    """为一个 LLM 批次建立短 ID，并保护其英文原文的 HTML 标签。"""
    block_by_alias: Dict[str, Any] = {}
    source_by_alias: Dict[str, str] = {}
    html_codec_by_alias: Dict[str, HtmlPlaceholderCodec] = {}

    for index, block in enumerate(blocks, start=1):
        alias = f"BLOCK_{index:03d}"
        source_text = str(getattr(block, "en_block", "") or "")
        tags = tuple(
            source_text[start:end]
            for start, end in _find_html_tag_spans(source_text)
        )

        block_by_alias[alias] = block
        if tags:
            codec = HtmlPlaceholderCodec(tags)
            html_codec_by_alias[alias] = codec
            source_by_alias[alias] = codec.protect(source_text)
        else:
            source_by_alias[alias] = source_text

    return BatchPromptContext(
        block_by_alias=block_by_alias,
        source_by_alias=source_by_alias,
        html_codec_by_alias=html_codec_by_alias,
    )
