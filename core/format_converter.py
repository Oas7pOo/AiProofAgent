import json
import csv
import logging
import re
import os
from typing import List, Optional, Dict, Any
from dataclasses import asdict

from models.document import TranslationBlock
from core.term_manager import TermManager

logger = logging.getLogger("AiProofAgent.FormatConverter")

class FormatConverter:
    """
    格式转换器，取代旧版的 io_utils 和 data_converter。
    仅围绕核心 DTO (TranslationBlock) 进行持久化和导出。
    """

    @staticmethod
    def save_to_json(blocks: List[TranslationBlock], file_path: str, old_terms: Optional[TermManager] = None, new_terms: Optional[TermManager] = None):
        """将一校/二校中的 TranslationBlock 列表保存为 JSON 文件，用于中断恢复"""
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
                    "stage": "proofread1",
                    "saved_at": "2026-04-02"
                },
                "terms": {
                    "old_terms": old_terms_entries,
                    "new_terms": new_terms_entries
                },
                "items": [asdict(block) for block in blocks]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"成功保存 {len(blocks)} 个数据块状态到 {file_path}")
        except Exception as e:
            logger.error(f"保存 JSON 失败: {e}")
            raise

    @staticmethod
    def load_from_json(file_path: str) -> tuple:
        """从保存的 JSON 中间文件恢复数据流"""
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

    @staticmethod
    def export_to_markdown(blocks: List[TranslationBlock], file_path: str, prefer_proofread: bool = True):
        """
        将数据导出为 Markdown 文档，与旧版本格式一致。
        prefer_proofread: 若为 True，则优先输出处理过的最终译文，否则退化为原文/初步识别结果。
        """
        try:
            import re
            header_pat = re.compile(r"^(#{1,6})\s+(.*)", re.DOTALL)
            clean_pat = re.compile(r"^#+\s*")
            
            title = os.path.splitext(os.path.basename(file_path))[0]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"# 校对报告: {title}\n\n")
                f.write("> 目录结构基于原文 Markdown 标记还原\n\n")
                
                for block in blocks:
                    original = block.en_block.strip()
                    proof = block.proofread_zh or block.proofread1_zh or block.zh_block or ""
                    proof = proof.strip()
                    note = block.proofread_note or block.proofread1_note or ""
                    note = note.strip()
                    key = block.key
                    
                    match = header_pat.match(original)
                    
                    if match:
                        hashes = match.group(1)
                        clean_original = match.group(2).strip()
                        
                        clean_proof = clean_pat.sub("", proof).strip()
                        display_title = clean_proof if clean_proof else clean_original
                        
                        f.write(f"{hashes} {display_title}\n\n")
                        f.write(f"*{clean_original}* `[{key}]`\n\n")
                        
                        if note:
                            f.write(f"> 标题建议: {note}\n\n")
                    else:
                        f.write(f"**[{key}]**\n")
                        f.write(f"> 原文: {original}\n")
                        
                        clean_proof_body = clean_pat.sub("", proof).strip()
                        if clean_proof_body:
                            f.write(f"> 校对: **{clean_proof_body}**\n")
                        
                        if note:
                            f.write(f"> *建议: {note}*\n")
                        f.write("\n")
            logger.info(f"成功导出最终文档至: {file_path}")
        except Exception as e:
            logger.error(f"导出 Markdown 失败: {e}")
            raise
    
    @staticmethod
    def load_from_csv(file_path: str) -> List[TranslationBlock]:
        """
        从 CSV 文件加载数据，支持 Paratranz 格式和通用格式
        支持 2-4 列的 CSV：
        - 2列：key, 原文
        - 3列：key, 原文, 译文
        - 4列：key, 原文, 译文, 注释
        支持混合格式：前几行可能只有2列（标题/前言），后面有3列（正文）
        跳过以 # 开头的注释行
        """
        try:
            blocks = []
            with open(file_path, 'r', encoding='utf-8') as f:
                # 直接使用 csv.reader 读取文件
                reader = csv.reader(f)
                
                for i, row in enumerate(reader):
                    # 跳过空行
                    if not row:
                        continue
                    
                    # 检查第一列是否是注释
                    if row[0].strip().startswith('#'):
                        continue
                    
                    # 按列索引处理，支持混合格式
                    key = str(i+1)  # 默认key
                    en_block = ''
                    zh_block = ''
                    
                    # 处理不同列数的行
                    if len(row) >= 1:
                        key = row[0].strip() or str(i+1)
                    if len(row) >= 2:
                        en_block = row[1].strip()
                    if len(row) >= 3:
                        zh_block = row[2].strip()
                    # 第4列是注释，暂不处理
                    
                    # 跳过空内容的块
                    if not en_block and not zh_block:
                        continue
                    
                    block = TranslationBlock(
                        key=key,
                        en_block=en_block,
                        zh_block=zh_block
                    )
                    blocks.append(block)
            
            logger.info(f"成功从 {file_path} 加载 {len(blocks)} 个数据块")
            return blocks
        except Exception as e:
            logger.error(f"加载 CSV 失败: {e}")
            raise
    
    @staticmethod
    def load_from_js(file_path: str) -> List[TranslationBlock]:
        """
        从 JS 文件加载数据，支持 const translations = [...] 格式
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 JSON 部分
            match = re.search(r'const\s+translations\s*=\s*(\[.*?\]);', content, re.DOTALL)
            if not match:
                raise ValueError("JS 文件格式不正确，未找到 translations 数组")
            
            json_str = match.group(1)
            data = json.loads(json_str)
            
            blocks = []
            for i, item in enumerate(data):
                key = item.get('key', str(i+1))
                en_block = item.get('original', '')
                zh_block = item.get('translation', '')
                
                block = TranslationBlock(
                    key=key,
                    en_block=en_block,
                    zh_block=zh_block
                )
                blocks.append(block)
            
            logger.info(f"成功从 {file_path} 加载 {len(blocks)} 个数据块")
            return blocks
        except Exception as e:
            logger.error(f"加载 JS 失败: {e}")
            raise
    
    @staticmethod
    def load_from_file(file_path: str) -> List[TranslationBlock]:
        """
        根据文件扩展名自动选择加载方法
        """
        if file_path.lower().endswith('.csv'):
            return FormatConverter.load_from_csv(file_path)
        elif file_path.lower().endswith('.js'):
            return FormatConverter.load_from_js(file_path)
        elif file_path.lower().endswith('.json'):
            blocks, _, _ = FormatConverter.load_from_json(file_path)
            return blocks
        else:
            raise ValueError(f"不支持的文件格式: {file_path}")
    
    @staticmethod
    def export_to_js(blocks: List[TranslationBlock], file_path: str):
        """
        将数据导出为 JS 文件，格式为 const translations = [...]
        """
        try:
            js_data = []
            for block in blocks:
                # 使用最高完成度的译文
                translation = block.proofread_zh or block.proofread1_zh or block.zh_block or ""
                js_data.append({
                    "key": block.key,
                    "original": block.en_block,
                    "translation": translation,
                    "stage": block.stage
                })
            
            js_content = f"const translations = {json.dumps(js_data, ensure_ascii=False, indent=2)};"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(js_content)
            logger.info(f"成功导出 JS 文件至: {file_path}")
        except Exception as e:
            logger.error(f"导出 JS 失败: {e}")
            raise
    
    @staticmethod
    def export_new_terms(blocks: List[TranslationBlock], file_path: str):
        """
        从数据块中提取新术语并导出为 JSON 文件，与旧版本格式一致。
        """
        try:
            all_terms = []
            for block in blocks:
                raw_terms = block.new_terms
                if raw_terms and isinstance(raw_terms, list):
                    all_terms.extend(raw_terms)
            
            seen = set()
            unique_terms = []
            for t in all_terms:
                if not isinstance(t, dict):
                    continue
                
                term = t.get("term", "").strip()
                if not term:
                    continue
                
                k = term.lower()
                if k in seen:
                    continue  # 同一英文术语多次出现：只保留第一次
                seen.add(k)
                
                unique_terms.append({
                    "term": term,
                    "translation": t.get("translation", "").strip(),
                    "note": t.get("note", "").strip(),
                })
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(unique_terms, f, ensure_ascii=False, indent=2)
            logger.info(f"成功导出新术语至: {file_path}")
        except Exception as e:
            logger.error(f"导出新术语失败: {e}")
            raise
    
    @staticmethod
    def export_final_json(blocks: List[TranslationBlock], file_path: str):
        """
        导出最终 JSON 文件，与旧版本格式一致。
        """
        try:
            final_list = []
            for block in blocks:
                final_list.append({
                    "key": block.key,
                    "original": block.en_block,
                    "translation": block.zh_block,
                    "proofread": block.proofread_zh or block.proofread1_zh or "",
                    "suggestion": block.proofread_note or block.proofread1_note or "",
                })
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(final_list, f, ensure_ascii=False, indent=2)
            logger.info(f"成功导出最终 JSON 至: {file_path}")
        except Exception as e:
            logger.error(f"导出最终 JSON 失败: {e}")
            raise