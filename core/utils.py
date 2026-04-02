#!/usr/bin/env python3
# 通用工具函数

import json
import logging
from typing import List, Dict, Any, Optional
from models.document import TranslationBlock
from models.term import TermEntry

logger = logging.getLogger("AiProofAgent.Utils")

# 构建术语匹配的通用函数
def match_terms_for_block(block: TranslationBlock, old_terms, new_terms) -> tuple:
    """
    为单个块匹配术语，返回 (old_hits, new_hits)
    """
    # 为每个块单独匹配术语
    block_old_hits = old_terms.match_terms(block.en_block)
    block_new_hits = new_terms.match_terms(block.en_block)
    
    # 旧术语优先，移除与旧术语重复的新术语
    block_old_terms_set = set(t.term for t in block_old_hits)
    block_new_hits = [t for t in block_new_hits if t.term not in block_old_terms_set]
    
    return block_old_hits, block_new_hits

# 格式化术语的通用函数
def format_terms(terms: List[TermEntry]) -> str:
    """
    格式化术语列表为字符串
    """
    if not terms:
        return "无"
    # 去重 + 保序
    seen = set()
    out_lines = []
    for t in terms:
        key = str(t.term).strip()
        if not key or key in seen:
            continue
        zh = str(t.translation).strip()
        note = f" ({t.note})" if t.note else ""
        out_lines.append(f"- {key}: {zh}{note}")
        seen.add(key)
    return "\n".join(out_lines)

# 提取新术语的通用函数
def extract_new_terms(blocks: List[TranslationBlock]) -> List[Dict[str, str]]:
    """
    从数据块中提取新术语
    """
    new_terms = []
    seen_terms = set()
    
    for block in blocks:
        if hasattr(block, 'new_terms') and block.new_terms:
            for term in block.new_terms:
                term_str = term.get('term', '').strip()
                if term_str and term_str not in seen_terms:
                    seen_terms.add(term_str)
                    new_terms.append(term)
    
    return new_terms

# 保存数据到JSON的通用函数
def save_data_to_json(blocks: List[TranslationBlock], file_path: str, old_terms=None, new_terms=None):
    """
    保存数据到JSON文件
    """
    try:
        # 提取术语信息
        old_terms_entries = []
        if old_terms:
            for term in old_terms.terms:
                old_terms_entries.append({
                    "term": term.term,
                    "translation": term.translation,
                    "note": term.note
                })
        
        new_terms_entries = []
        if new_terms:
            for term in new_terms.terms:
                new_terms_entries.append({
                    "term": term.term,
                    "translation": term.translation,
                    "note": term.note
                })
        
        # 构建存档数据
        data = {
            "meta": {
                "stage": "proofread",
                "saved_at": "2026-04-02"
            },
            "terms": {
                "old_terms": old_terms_entries,
                "new_terms": new_terms_entries
            },
            "items": [vars(block) for block in blocks]
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"成功保存 {len(blocks)} 个数据块状态到 {file_path}")
    except Exception as e:
        logger.error(f"保存 JSON 失败: {e}")
        raise

# 加载数据从JSON的通用函数
def load_data_from_json(file_path: str) -> tuple:
    """
    从JSON文件加载数据
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取术语信息
        old_terms_entries = []
        new_terms_entries = []
        
        if isinstance(data, dict):
            terms = data.get("terms", {})
            old_terms_entries = terms.get("old_terms", [])
            new_terms_entries = terms.get("new_terms", [])
            data = data.get("items", data)
        
        # 加载数据块
        if isinstance(data, list):
            blocks = []
            for item in data:
                # 过滤并映射字段
                filtered_item = {}
                # 映射原始字段
                if "original" in item:
                    filtered_item["en_block"] = item["original"]
                if "translation" in item:
                    filtered_item["zh_block"] = item["translation"]
                # 复制其他字段
                for key in ["key", "page", "block_num", "en_block", "zh_block", "proofread1_zh", "proofread1_note", "new_terms", "proofread_zh", "proofread_note", "stage"]:
                    if key in item:
                        filtered_item[key] = item[key]
                # 创建 TranslationBlock 实例
                blocks.append(TranslationBlock(**filtered_item))
        else:
            blocks = []
        
        logger.info(f"成功从 {file_path} 恢复 {len(blocks)} 个数据块")
        return blocks, old_terms_entries, new_terms_entries
    except Exception as e:
        logger.error(f"加载 JSON 失败: {e}")
        raise
