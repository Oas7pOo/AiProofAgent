#!/usr/bin/env python3
# 测试实际工作流中的术语提取功能

from core.term_manager import TermManager
from core.utils import match_terms_for_block, format_terms
from models.document import TranslationBlock
from models.term import TermEntry

# 测试文本
text = "Hear, O adventurer, of your wyrd and the fate of all those who seek to oppose what is written for them in the blood of dragons: The mortal world of Midgard is a place of heroes, and heroes often fall like glittering coins into the claws of Veles, the first of dragons! Where scales rustle and slide, have a care, lest you enter the halls of Valhalla earlier than you might wish."

# 创建 TranslationBlock
block = TranslationBlock(
    key="worldbook_P001_B018",
    en_block=text,
    zh_block=""
)

# 创建 TermManager 实例并添加术语
old_terms = TermManager()
new_terms = TermManager()

# 添加一些术语到旧术语表
old_terms_list = [
    TermEntry(term="Midgard", translation="米德加尔特"),
    TermEntry(term="Valhalla", translation="瓦尔哈拉")
]
old_terms.terms = old_terms_list
old_terms._build_matchers()

# 添加一些术语到新术语表
new_terms_list = [
    TermEntry(term="wyrd", translation="命运"),
    TermEntry(term="Veles", translation="维勒斯")
]
new_terms.terms = new_terms_list
new_terms._build_matchers()

# 测试术语匹配
block_old_hits, block_new_hits = match_terms_for_block(block, old_terms, new_terms)

# 格式化术语
block_old_terms_str = format_terms(block_old_hits)
block_new_terms_str = format_terms(block_new_hits)

# 打印结果
print("测试工作流中的术语提取功能:")
print(f"\n原文: {text}")
print(f"\n匹配到的旧术语:")
print(block_old_terms_str)
print(f"\n匹配到的新术语:")
print(block_new_terms_str)

# 模拟构建 prompt
prompt = f"""--- BLOCK_ID: {block.key} ---
原文: {block.en_block}
原译文: {block.zh_block}
参考术语: {block_old_terms_str}
新术语建议: {block_new_terms_str}
"""

print("\n构建的 prompt 片段:")
print(prompt)
