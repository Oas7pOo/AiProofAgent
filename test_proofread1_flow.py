#!/usr/bin/env python3
# 测试修改后的一校流程

from core.term_manager import TermManager
from core.utils import match_terms_for_block, format_terms
from models.document import TranslationBlock
from models.term import TermEntry

# 测试文本
text = "Sated Fang turned to the gearforged oracle. \"Just as you saw in your vision,\" she said. \"It's Kaldgate.\""

# 创建 TranslationBlock
block = TranslationBlock(
    key="worldbook_P002_B013",
    en_block=text,
    zh_block=""
)

# 创建 TermManager 实例
old_terms = TermManager()
new_terms = TermManager()

# 添加一些术语到旧术语表
old_terms_list = [
    TermEntry(term="Sated Fang", translation="饱足之牙"),
    TermEntry(term="Kaldgate", translation="卡尔德盖特")
]
old_terms.terms = old_terms_list
old_terms._build_matchers()

# 添加一些术语到新术语表（模拟已有的新术语）
new_terms_list = [
    TermEntry(term="Jana", translation="雅娜"),
    TermEntry(term="Rava", translation="拉瓦")
]
new_terms.terms = new_terms_list
new_terms._build_matchers()

print("测试一校流程（只使用旧术语）:")
print(f"旧术语表: {[t.term for t in old_terms.terms]}")
print(f"新术语表: {[t.term for t in new_terms.terms]}")
print(f"原文: {text}")

# 测试术语匹配（一校只使用旧术语）
block_old_hits, _ = match_terms_for_block(block, old_terms, new_terms)
block_old_terms_str = format_terms(block_old_hits)

print(f"\n一校参考术语: {block_old_terms_str}")

# 模拟构建一校 prompt
prompt = f"""
【待处理内容】
--- BLOCK_ID: {block.key} ---
原文: {block.en_block}
原译文: {block.zh_block}
参考术语: {block_old_terms_str}

【处理逻辑 - 请严格遵守】
对于每一个 Block，请先判断其是否可以正常处理，并从以下两种模式中选择一种输出：

模式 A：正常校对（绝大多数情况）
- 适用场景：原文可读，且你能提供有效的校对建议。
- proofread_zh：输出修正后的译文。
- proofread_note：输出具体的修改原因（如：术语修正/语法优化/风格调整）。请不要写"无"、"没问题"，如果没有修改，请留空字符串。
- new_terms: 仅当该块中出现明确"专有名词/术语/人名/地名"且不在术语表内时才输出；否则 []。
  new_terms 每项必须是：{'term': '英文术语', 'translation': '中文译名', 'note': '可选备注'}

模式 B：异常报错（极少数情况）
- 适用场景：原文全是乱码、原文不仅是外语还是无法理解的字符。
- proofread_zh：必须输出固定标签 "[BLOCK_ERROR]"。
- proofread_note：必须说明无法处理的具体技术原因（如：GARBLED_TEXT, SAFETY_FILTER）。

【输出格式】
必须输出一个纯 JSON 列表，不要包含 Markdown 标记。
[{{
  "BLOCK_ID": "保持原样",
  "proofread_zh": "修正后的译文 或 [BLOCK_ERROR]",
  "proofread_note": "语言学备注 或 错误原因",
  "new_terms": []
}}]
"""

print("\n构建的一校 prompt（部分）:")
print(prompt[:500] + "...")
