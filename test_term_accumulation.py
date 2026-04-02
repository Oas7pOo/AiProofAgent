#!/usr/bin/env python3
# 测试术语累积和重用功能

from core.term_manager import TermManager
from models.term import TermEntry

# 模拟 LLM 返回的新术语
new_terms_from_llm = [
    {
        "term": "Sated Fang",
        "translation": "饱足之牙",
        "note": "角色名"
    },
    {
        "term": "Kaldgate",
        "translation": "卡尔德盖特",
        "note": "地名"
    },
    {
        "term": "Jana",
        "translation": "雅娜",
        "note": "角色名"
    }
]

# 创建 TermManager 实例
new_terms = TermManager()
print(f"初始术语数量: {len(new_terms.terms)}")

# 模拟处理 LLM 返回的新术语
for term_data in new_terms_from_llm:
    term = term_data.get("term", "").strip()
    translation = term_data.get("translation", "").strip()
    note = term_data.get("note", "").strip()
    if term and translation:
        # 检查是否已存在
        existing_terms = [t for t in new_terms.terms if t.term == term]
        if not existing_terms:
            new_terms.terms.append(TermEntry(
                term=term,
                translation=translation,
                note=note
            ))
            print(f"添加新术语: {term} -> {translation}")
        else:
            print(f"术语已存在: {term}")

# 重新构建 matcher
new_terms._build_matchers()
print(f"处理后术语数量: {len(new_terms.terms)}")

# 测试术语匹配
test_text = "Sated Fang turned to Jana. They were heading to Kaldgate."
matches = new_terms.match_terms(test_text)
print(f"\n测试文本: {test_text}")
print(f"匹配到的术语: {[term.term for term in matches]}")

# 测试重复添加相同术语
print("\n测试重复添加相同术语:")
duplicate_term = {
    "term": "Sated Fang",
    "translation": "饱足之牙",
    "note": "角色名"
}

term = duplicate_term.get("term", "").strip()
translation = duplicate_term.get("translation", "").strip()
note = duplicate_term.get("note", "").strip()
if term and translation:
    existing_terms = [t for t in new_terms.terms if t.term == term]
    if not existing_terms:
        new_terms.terms.append(TermEntry(
            term=term,
            translation=translation,
            note=note
        ))
        print(f"添加新术语: {term} -> {translation}")
    else:
        print(f"术语已存在: {term}")

print(f"最终术语数量: {len(new_terms.terms)}")
