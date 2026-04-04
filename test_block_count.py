#!/usr/bin/env python3
"""
测试程序：验证源文件与一校二校存档的 block 数量一致性
"""

import json
import sys
from pathlib import Path
from typing import Tuple, Optional


def load_json_file(file_path: str) -> Tuple[Optional[list], Optional[dict], str]:
    """
    加载 JSON 文件，支持两种格式：
    1. 简单列表格式：[{"key": "...", ...}, ...]
    2. 存档格式：{"meta": {...}, "terms": {...}, "items": [...]}
    
    返回: (items_list, full_data, error_message)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            # 简单列表格式（源文件）
            return data, None, ""
        elif isinstance(data, dict):
            # 存档格式
            items = data.get("items", [])
            return items, data, ""
        else:
            return None, None, f"未知的数据格式: {type(data)}"
            
    except FileNotFoundError:
        return None, None, f"文件不存在: {file_path}"
    except json.JSONDecodeError as e:
        return None, None, f"JSON 解析错误: {e}"
    except Exception as e:
        return None, None, f"读取错误: {e}"


def count_blocks(file_path: str) -> Tuple[int, str]:
    """
    计算文件中的 block 数量
    返回: (block_count, error_message)
    """
    items, _, error = load_json_file(file_path)
    
    if error:
        return -1, error
    
    if items is None:
        return -1, "无法获取 items"
    
    return len(items), ""


def compare_block_counts(source_file: str, proof1_file: Optional[str] = None, 
                         proof2_file: Optional[str] = None) -> bool:
    """
    比较源文件与一校二校存档的 block 数量
    返回: True 如果所有检查通过
    """
    print("=" * 60)
    print("Block 数量一致性测试")
    print("=" * 60)
    
    all_passed = True
    
    # 1. 检查源文件
    print(f"\n📄 源文件: {source_file}")
    source_count, error = count_blocks(source_file)
    if error:
        print(f"   ❌ 错误: {error}")
        return False
    print(f"   ✅ Block 数量: {source_count}")
    
    # 2. 检查一校存档
    if proof1_file:
        print(f"\n📄 一校存档: {proof1_file}")
        if not Path(proof1_file).exists():
            print(f"   ⚠️  文件不存在，跳过检查")
        else:
            proof1_count, error = count_blocks(proof1_file)
            if error:
                print(f"   ❌ 错误: {error}")
                all_passed = False
            else:
                print(f"   ✅ Block 数量: {proof1_count}")
                if source_count != proof1_count:
                    print(f"   ❌ 数量不匹配! 源文件: {source_count}, 一校: {proof1_count}")
                    all_passed = False
                else:
                    print(f"   ✅ 数量匹配")
    
    # 3. 检查二校存档
    if proof2_file:
        print(f"\n📄 二校存档: {proof2_file}")
        if not Path(proof2_file).exists():
            print(f"   ⚠️  文件不存在，跳过检查")
        else:
            proof2_count, error = count_blocks(proof2_file)
            if error:
                print(f"   ❌ 错误: {error}")
                all_passed = False
            else:
                print(f"   ✅ Block 数量: {proof2_count}")
                if source_count != proof2_count:
                    print(f"   ❌ 数量不匹配! 源文件: {source_count}, 二校: {proof2_count}")
                    all_passed = False
                else:
                    print(f"   ✅ 数量匹配")
    
    # 4. 检查一校和二校之间的一致性
    if proof1_file and proof2_file and Path(proof1_file).exists() and Path(proof2_file).exists():
        print(f"\n📊 一校 vs 二校:")
        proof1_count, _ = count_blocks(proof1_file)
        proof2_count, _ = count_blocks(proof2_file)
        if proof1_count != proof2_count:
            print(f"   ❌ 数量不匹配! 一校: {proof1_count}, 二校: {proof2_count}")
            all_passed = False
        else:
            print(f"   ✅ 数量匹配 ({proof1_count})")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有检查通过!")
    else:
        print("❌ 存在不一致!")
    print("=" * 60)
    
    return all_passed


def detailed_comparison(source_file: str, proof1_file: Optional[str] = None,
                        proof2_file: Optional[str] = None) -> bool:
    """
    详细比较：检查每个 block 的 key 是否一致
    """
    print("\n" + "=" * 60)
    print("详细 Key 对比")
    print("=" * 60)
    
    # 加载源文件 keys
    source_items, _, error = load_json_file(source_file)
    if error:
        print(f"❌ 无法加载源文件: {error}")
        return False
    
    source_keys = {item.get("key", f"index_{i}") for i, item in enumerate(source_items)}
    print(f"\n📄 源文件 Keys: {len(source_keys)} 个")
    
    all_passed = True
    
    # 检查一校
    if proof1_file and Path(proof1_file).exists():
        proof1_items, _, error = load_json_file(proof1_file)
        if error:
            print(f"❌ 无法加载一校存档: {error}")
            all_passed = False
        else:
            proof1_keys = {item.get("key", f"index_{i}") for i, item in enumerate(proof1_items)}
            print(f"\n📄 一校存档 Keys: {len(proof1_keys)} 个")
            
            missing_in_proof1 = source_keys - proof1_keys
            extra_in_proof1 = proof1_keys - source_keys
            
            if missing_in_proof1:
                print(f"   ❌ 一校缺少 {len(missing_in_proof1)} 个 blocks:")
                for key in sorted(missing_in_proof1)[:5]:  # 只显示前5个
                    print(f"      - {key}")
                if len(missing_in_proof1) > 5:
                    print(f"      ... 还有 {len(missing_in_proof1) - 5} 个")
                all_passed = False
            
            if extra_in_proof1:
                print(f"   ⚠️  一校多出 {len(extra_in_proof1)} 个 blocks:")
                for key in sorted(extra_in_proof1)[:5]:
                    print(f"      - {key}")
                if len(extra_in_proof1) > 5:
                    print(f"      ... 还有 {len(extra_in_proof1) - 5} 个")
    
    # 检查二校
    if proof2_file and Path(proof2_file).exists():
        proof2_items, _, error = load_json_file(proof2_file)
        if error:
            print(f"❌ 无法加载二校存档: {error}")
            all_passed = False
        else:
            proof2_keys = {item.get("key", f"index_{i}") for i, item in enumerate(proof2_items)}
            print(f"\n📄 二校存档 Keys: {len(proof2_keys)} 个")
            
            missing_in_proof2 = source_keys - proof2_keys
            extra_in_proof2 = proof2_keys - source_keys
            
            if missing_in_proof2:
                print(f"   ❌ 二校缺少 {len(missing_in_proof2)} 个 blocks:")
                for key in sorted(missing_in_proof2)[:5]:
                    print(f"      - {key}")
                if len(missing_in_proof2) > 5:
                    print(f"      ... 还有 {len(missing_in_proof2) - 5} 个")
                all_passed = False
            
            if extra_in_proof2:
                print(f"   ⚠️  二校多出 {len(extra_in_proof2)} 个 blocks:")
                for key in sorted(extra_in_proof2)[:5]:
                    print(f"      - {key}")
                if len(extra_in_proof2) > 5:
                    print(f"      ... 还有 {len(extra_in_proof2) - 5} 个")
    
    print("\n" + "=" * 60)
    return all_passed


def main():
    """主函数"""
    # 默认文件路径
    default_source = "data/midgard worldbook.json"
    default_proof1 = "outputs/midgard worldbook_proof1.json"
    default_proof2 = "outputs/midgard worldbook_proof2.json"
    
    # 从命令行参数获取文件路径
    source_file = sys.argv[1] if len(sys.argv) > 1 else default_source
    proof1_file = sys.argv[2] if len(sys.argv) > 2 else default_proof1
    proof2_file = sys.argv[3] if len(sys.argv) > 3 else default_proof2
    
    print("\n🔍 Block 数量一致性测试工具")
    print(f"源文件: {source_file}")
    print(f"一校存档: {proof1_file}")
    print(f"二校存档: {proof2_file}")
    
    # 基本数量比较
    basic_passed = compare_block_counts(source_file, proof1_file, proof2_file)
    
    # 详细 key 对比（可选）
    if "--detailed" in sys.argv or "-d" in sys.argv:
        detailed_passed = detailed_comparison(source_file, proof1_file, proof2_file)
    else:
        detailed_passed = True
        print("\n💡 使用 --detailed 或 -d 参数进行详细的 key 对比")
    
    # 返回退出码
    sys.exit(0 if (basic_passed and detailed_passed) else 1)


if __name__ == "__main__":
    main()

'''
基本使用 （只比较数量）：

```
python test_block_count.py
```
指定文件路径 ：

```
python test_block_count.py 源文件.
json 一校存档.json 二校存档.json
```
详细对比 （检查每个 block 的 key 是否一致）：

```
python test_block_count.py 
--detailed
# 或
python test_block_count.py -d
```
'''