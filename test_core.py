#!/usr/bin/env python3
# 测试核心功能

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.term_manager import TermManager
from core.format_converter import FormatConverter
from models.document import TranslationBlock

# 测试术语管理
def test_term_manager():
    print("\n=== 测试术语管理 ===")
    term_manager = TermManager()
    
    # 添加一些测试术语
    term_manager.terms.append(type('obj', (object,), {'term': 'Rapier', 'translation': '刺剑', 'note': '轻剑'})())
    term_manager.terms.append(type('obj', (object,), {'term': 'Wizard', 'translation': '法师', 'note': '职业'})())
    term_manager.terms.append(type('obj', (object,), {'term': 'Dragon', 'translation': '龙', 'note': '生物'})())
    
    # 构建匹配器
    term_manager._build_matchers()
    
    # 测试术语匹配
    test_text = "The wizard wielded a rapier against the dragon"
    matched_terms = term_manager.match_terms(test_text)
    
    print(f"测试文本: {test_text}")
    print(f"匹配到的术语: {[t.term for t in matched_terms]}")
    
    return len(matched_terms) > 0

# 测试格式转换器
def test_format_converter():
    print("\n=== 测试格式转换器 ===")
    
    # 创建测试数据块
    blocks = [
        TranslationBlock(
            key="1",
            en_block="Hello world",
            zh_block="你好世界",
            proofread1_zh="你好，世界",
            proofread1_note="添加逗号",
            new_terms=[{"term": "World", "translation": "世界", "note": "名词"}]
        ),
        TranslationBlock(
            key="2",
            en_block="This is a test",
            zh_block="这是一个测试",
            proofread1_zh="这是一个测试",
            proofread1_note="",
            new_terms=[]
        )
    ]
    
    # 测试保存到JSON
    test_json = "test_archive.json"
    term_manager = TermManager()
    term_manager.terms.append(type('obj', (object,), {'term': 'Test', 'translation': '测试', 'note': '名词'})())
    
    try:
        FormatConverter.save_to_json(blocks, test_json, term_manager, term_manager)
        print(f"成功保存到 {test_json}")
        
        # 测试从JSON加载
        loaded_blocks, old_terms, new_terms = FormatConverter.load_from_json(test_json)
        print(f"成功加载 {len(loaded_blocks)} 个数据块")
        print(f"加载到 {len(old_terms)} 条旧术语")
        print(f"加载到 {len(new_terms)} 条新术语")
        
        # 清理测试文件
        if os.path.exists(test_json):
            os.remove(test_json)
        
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False

# 运行测试
if __name__ == "__main__":
    print("开始测试核心功能...")
    
    term_test_passed = test_term_manager()
    converter_test_passed = test_format_converter()
    
    print("\n=== 测试结果 ===")
    print(f"术语管理测试: {'通过' if term_test_passed else '失败'}")
    print(f"格式转换器测试: {'通过' if converter_test_passed else '失败'}")
    
    if term_test_passed and converter_test_passed:
        print("\n所有测试通过！")
        sys.exit(0)
    else:
        print("\n测试失败！")
        sys.exit(1)
