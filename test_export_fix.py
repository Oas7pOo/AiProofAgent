import json
import os
from core.format_converter import FormatConverter
from models.document import TranslationBlock

# 创建一个测试存档文件
test_archive = "test_archive.json"

test_blocks = [
    TranslationBlock(
        key="1",
        en_block="Test term",
        zh_block="测试术语",
        proofread1_zh="校对术语",
        proofread_zh="最终校对术语",
        stage=2
    )
]

# 保存测试存档
FormatConverter.save_to_json(test_blocks, test_archive)
print(f"创建测试存档: {test_archive}")

# 测试load_from_json方法
try:
    blocks, old_terms, new_terms = FormatConverter.load_from_json(test_archive)
    print(f"成功加载存档，获取到 {len(blocks)} 个数据块")
    print(f"旧术语数量: {len(old_terms)}")
    print(f"新术语数量: {len(new_terms)}")
    
    # 测试导出为JS
    test_js = "test_export.js"
    FormatConverter.export_to_js(blocks, test_js)
    print(f"成功导出JS: {test_js}")
    
    # 清理测试文件
    os.remove(test_archive)
    os.remove(test_js)
    print("测试完成，清理测试文件")
    
    print("修复验证成功！")
except Exception as e:
    print(f"测试失败: {e}")
    # 清理测试文件
    if os.path.exists(test_archive):
        os.remove(test_archive)
    if os.path.exists("test_export.js"):
        os.remove("test_export.js")
