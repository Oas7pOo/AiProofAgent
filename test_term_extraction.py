#!/usr/bin/env python3
# 测试术语提取功能

from core.term_manager import TermManager
from models.term import TermEntry

# 测试文本
text = "Hear, O adventurer, of your wyrd and the fate of all those who seek to oppose what is written for them in the blood of dragons: The mortal world of Midgard is a place of heroes, and heroes often fall like glittering coins into the claws of Veles, the first of dragons! Where scales rustle and slide, have a care, lest you enter the halls of Valhalla earlier than you might wish."

# 创建 TermManager 实例
term_manager = TermManager()

# 添加一些术语
terms = [
    TermEntry(term="wyrd", translation="命运"),
    TermEntry(term="Midgard", translation="米德加尔特"),
    TermEntry(term="Veles", translation="维勒斯"),
    TermEntry(term="Valhalla", translation="瓦尔哈拉")
]

# 手动添加术语到 term_manager
term_manager.terms = terms
term_manager._build_matchers()

# 测试术语匹配
matches = term_manager.match_terms(text)
print("匹配到的术语:")
for term in matches:
    print(f"- {term.term}: {term.translation}")

# 测试术语提取功能
print("\n测试术语提取功能...")
print("文本中可能的术语: wyrd, Midgard, Veles, Valhalla")
print(f"匹配到的术语数量: {len(matches)}")
