#!/usr/bin/env python3
# 测试完整的术语匹配流程

from core.term_manager import TermManager
from core.utils import match_terms_for_block, format_terms
from models.document import TranslationBlock
from models.term import TermEntry

# 测试文本 - 与日志中的文本一致
texts = [
    "Sated Fang turned to the gearforged oracle. \"Just as you saw in your vision,\" she said. \"It's Kaldgate.\"",
    "Fire kindled in Jana's crystal eyes. \"At last,\" she said. \"If Rava will, we may this day learn what troubles the World Serpent in its sleep, and discover a way to turn back the tide of darkness that threatens the Free City.\" With that, she took off at a run and vanished over the rise. Jiro stumbled after her, until Sated Fang lifted him onto her shoulders and raced across the snow with a monk's effortless grace and the tireless endurance of the undead."
]

# 创建 TranslationBlock 实例
blocks = []
for i, text in enumerate(texts):
    block = TranslationBlock(
        key=f"test_block_{i}",
        en_block=text,
        zh_block=""
    )
    blocks.append(block)

# 创建 TermManager 实例
old_terms = TermManager()
new_terms = TermManager()

# 添加一些术语
terms = [
    TermEntry(term="Sated Fang", translation="饱足之牙"),
    TermEntry(term="Kaldgate", translation="卡尔德盖特"),
    TermEntry(term="Jana", translation="雅娜"),
    TermEntry(term="Rava", translation="拉瓦"),
    TermEntry(term="World Serpent", translation="世界巨蛇"),
    TermEntry(term="Free City", translation="自由城"),
    TermEntry(term="Jiro", translation="次郎")
]

# 添加术语到 old_terms
old_terms.terms = terms
old_terms._build_matchers()
print(f"已添加 {len(terms)} 个术语到术语表")

# 测试术语匹配
for block in blocks:
    print(f"\n测试块: {block.key}")
    print(f"原文: {block.en_block}")
    
    # 匹配术语
    block_old_hits, block_new_hits = match_terms_for_block(block, old_terms, new_terms)
    
    # 格式化术语
    block_old_terms_str = format_terms(block_old_hits)
    block_new_terms_str = format_terms(block_new_hits)
    
    print(f"匹配到的旧术语: {block_old_terms_str}")
    print(f"匹配到的新术语: {block_new_terms_str}")
    
    # 检查是否匹配到术语
    if block_old_terms_str == "无" and block_new_terms_str == "无":
        print("警告: 没有匹配到任何术语！")
    else:
        print("成功匹配到术语")

# 测试 TermManager 的 match_terms 方法
print("\n直接测试 TermManager.match_terms 方法:")
test_text = texts[0]
matches = old_terms.match_terms(test_text)
print(f"测试文本: {test_text}")
print(f"匹配到的术语: {[term.term for term in matches]}")
