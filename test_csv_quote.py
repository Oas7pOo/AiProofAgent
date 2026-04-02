#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试带双引号的CSV格式"""

import sys
sys.path.insert(0, '.')

from core.format_converter import FormatConverter
import os

# 测试用户提供的CSV格式
test_csv_content = """worldbook_P001_B001,# CREDITS,,
worldbook_P001_B002,LEAD DESIGNER Wolfgang Baur,,
worldbook_P001_B003,"DESIGNERS Dan Dillon, Richard Green, Jeff Grubb, Chris Harris, Jon Sawatsky, and Brian Suskind",,
worldbook_P001_B004,"Based on prior edition work by Wolfgang Baur, Jeff Grubb, Brandon Hodge, Christina Stiles, and Dan Voyce",,
"""

test_csv_path = "test_quote.csv"
with open(test_csv_path, 'w', encoding='utf-8') as f:
    f.write(test_csv_content)

print(f"创建测试CSV文件: {test_csv_path}")
print(f"CSV内容:\n{test_csv_content}")

# 测试加载
try:
    blocks = FormatConverter.load_from_csv(test_csv_path)
    print(f"\n成功加载 {len(blocks)} 个数据块")
    for block in blocks:
        print(f"  key={block.key}")
        print(f"  en_block={repr(block.en_block)}")
        print(f"  zh_block={repr(block.zh_block)}")
        print()
except Exception as e:
    print(f"加载失败: {e}")
    import traceback
    traceback.print_exc()

# 清理
os.remove(test_csv_path)
print(f"\n清理测试文件: {test_csv_path}")
