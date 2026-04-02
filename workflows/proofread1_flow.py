import json
import re
import threading
import logging
import csv
import time
from typing import List, Callable, Optional

from core.ocr_engine import PaddleOCREngine
from core.llm_engine import LlmEngine
from core.format_converter import FormatConverter
from core.term_manager import TermManager
from core.utils import match_terms_for_block, format_terms
from models.document import TranslationBlock
from models.term import TermEntry
from workflows.base_runner import BatchTaskRunner

logger = logging.getLogger("AiProofAgent.Proofread1")

class Proofread1Workflow:
    """
    一校业务编排层 (Proofread 1 Workflow)
    职责：协调 OCR/缓存读取 -> LLM 并发翻译 -> 进度持久化
    """
    def __init__(self, config_path="config.yaml"):
        from utils.config import ConfigManager
        cfg = ConfigManager(config_path)
        
        # 智能读取：同时查找嵌套格式和扁平格式
        def _get_val(keys, default):
            for k in keys:
                v = cfg.get(k)
                if v is not None and str(v).strip() != "":
                    return v
            return default
        
        max_workers = int(_get_val(["ai_max_workers", "llm.ai_max_workers"], 1))
        delay_seconds = int(_get_val(["time_wait", "llm.time_wait"], 10))
        max_blocks = int(_get_val(["max_blocks", "llm.max_blocks"], 10))
        max_chars = int(_get_val(["max_chars", "llm.max_chars"], 8000))
        
        self.ocr_engine = PaddleOCREngine(config_path)
        self.llm_engine = LlmEngine(config_path)
        self.runner = BatchTaskRunner(max_workers=max_workers, delay_seconds=delay_seconds)
        self.max_blocks = max_blocks
        self.max_chars = max_chars
        self.old_terms = TermManager()
        self.new_terms = TermManager()
        
        logger.info(f"一校流水线配置: max_workers={max_workers}, delay_seconds={delay_seconds}, max_blocks={max_blocks}, max_chars={max_chars}")

    def execute_async(self, 
                      file_path: str, 
                      out_path: str,
                      is_pdf: bool = True,
                      old_terms_path: str = "",
                      new_terms_path: str = "",
                      progress_callback: Optional[Callable[[int, int], None]] = None,
                      done_callback: Optional[Callable[[List[TranslationBlock]], None]] = None,
                      error_callback: Optional[Callable[[Exception], None]] = None):
        
        def _task():
            try:
                logger.info("启动一校流水线 (Proofread 1)...")
                
                # 保存输出路径和数据块为实例变量
                self.out_path = out_path
                
                # 加载术语文件
                if old_terms_path:
                    self.old_terms.load_terms(old_terms_path)
                    logger.info(f"已加载旧术语表: {old_terms_path}")
                if new_terms_path:
                    self.new_terms.load_terms(new_terms_path)
                    logger.info(f"已加载新术语表: {new_terms_path}")
                
                # 1. 加载或解析数据
                if is_pdf:
                    logger.info("检测到 PDF 输入，正在执行 OCR 和版面分析...")
                    blocks = self.ocr_engine.process_pdf(file_path)
                else:
                    logger.info(f"读取输入文件: {file_path}")
                    # 检查是否为存档文件（包含术语信息）
                    if file_path.lower().endswith('.json'):
                        # 从存档加载数据和术语
                        blocks, old_terms_entries, new_terms_entries = FormatConverter.load_from_json(file_path)
                        
                        # 恢复术语信息
                        if old_terms_entries:
                            for entry in old_terms_entries:
                                self.old_terms.terms.append(TermEntry(
                                term=entry.get("term", entry.get("en", "")),
                                translation=entry.get("translation", entry.get("zh", "")),
                                note=entry.get("note", "")
                            ))
                            self.old_terms._build_matchers()
                            logger.info(f"从存档恢复 {len(old_terms_entries)} 条旧术语")
                        
                        if new_terms_entries:
                            for entry in new_terms_entries:
                                self.new_terms.terms.append(TermEntry(
                                term=entry.get("term", entry.get("en", "")),
                                translation=entry.get("translation", entry.get("zh", "")),
                                note=entry.get("note", "")
                            ))
                            self.new_terms._build_matchers()
                            logger.info(f"从存档恢复 {len(new_terms_entries)} 条新术语")
                    else:
                        # 从其他格式文件加载数据
                        blocks = FormatConverter.load_from_file(file_path)
                        logger.info(f"从 {file_path} 加载 {len(blocks)} 个数据块")

                # 保存数据块为实例变量
                self.blocks = blocks
                
                # 2. 筛选未完成一校的块
                pending_blocks = [b for b in blocks if b.stage < 1]
                logger.info(f"任务分析完毕: 共 {len(blocks)} 个片段，需处理 {len(pending_blocks)} 个片段。")

                # 3. 分批处理
                if pending_blocks:
                    # 构建批次
                    batches = self._build_batches(pending_blocks)
                    logger.info(f"已将 {len(pending_blocks)} 个片段分为 {len(batches)} 个批次")
                    
                    # 保存初始状态
                    FormatConverter.save_to_json(blocks, out_path, self.old_terms, self.new_terms)
                    logger.info(f"已保存初始状态到: {out_path}")
                    
                    # 总块数
                    total_blocks = len(pending_blocks)
                    # 已完成块数
                    completed_blocks = 0
                    
                    # 自定义进度回调函数
                    def custom_progress_callback(completed_batches, total_batches):
                        nonlocal completed_blocks
                        # 计算已完成的块数
                        # 每个批次的平均大小
                        avg_batch_size = total_blocks / total_batches
                        # 已完成的块数
                        completed_blocks = int(completed_batches * avg_batch_size)
                        # 确保不超过总块数
                        completed_blocks = min(completed_blocks, total_blocks)
                        # 调用原始进度回调函数
                        if progress_callback:
                            progress_callback(completed_blocks, total_blocks)
                        # 记录日志
                        logger.info(f"校对进度: {completed_blocks}/{total_blocks}")
                    
                    # 执行并发处理
                    self.runner.run_sync(batches, self._process_batch, on_progress=custom_progress_callback)
                
                # 4. 保存到存档路径
                FormatConverter.save_to_json(blocks, out_path, self.old_terms, self.new_terms)
                
                logger.info(f"一校流水线全部完成，状态已保存至: {out_path}")
                if done_callback:
                    done_callback(blocks)
                    
            except Exception as e:
                logger.error(f"一校流水线发生致命错误: {e}", exc_info=True)
                if error_callback:
                    error_callback(e)

        # 在后台线程中独立运行，不阻塞主线程
        threading.Thread(target=_task, daemon=True).start()

    def _build_batches(self, blocks: List[TranslationBlock]) -> List[List[TranslationBlock]]:
        """根据 max_blocks 和 max_chars 构建批次"""
        batches = []
        current_batch = []
        current_chars = 0
        
        for block in blocks:
            # 计算当前块的字符数
            block_chars = len(block.en_block) + len(block.zh_block)
            
            # 如果当前批次已满，创建新批次
            if current_batch and (len(current_batch) >= self.max_blocks or current_chars + block_chars > self.max_chars):
                batches.append(current_batch)
                current_batch = []
                current_chars = 0
            
            # 添加当前块到批次
            current_batch.append(block)
            current_chars += block_chars
        
        # 添加最后一个批次
        if current_batch:
            batches.append(current_batch)
        
        return batches

    def _process_batch(self, batch: List[TranslationBlock]) -> List[TranslationBlock]:
        """处理一个批次的块，包含失败重试和任务拆分机制"""
        result = self._process_recursive(batch, depth=0)
        # 处理完一个批次后保存状态
        FormatConverter.save_to_json(self.blocks, self.out_path, self.old_terms, self.new_terms)
        logger.info(f"已保存批次处理状态到: {self.out_path}")
        return result
    
    def _process_recursive(self, batch: List[TranslationBlock], depth: int = 0) -> List[TranslationBlock]:
        """递归处理批次，包含失败重试和任务拆分机制"""
        if not batch:
            return batch
        
        MAX_RETRIES = 3
        
        for attempt in range(MAX_RETRIES):
            try:
                # 系统提示
                system_prompt = "你是一个严谨的本地化校对专家。你的任务是根据参考术语校对原文和译文。"
                
                # 构建批次 prompt
                blocks_text = []
                for block in batch:
                    # 为每个块单独匹配术语（一校只使用旧术语）
                    block_old_hits, _ = match_terms_for_block(block, self.old_terms, self.new_terms)
                    
                    # 格式化术语
                    block_old_terms_str = format_terms(block_old_hits)
                    
                    blocks_text.append(
                        f"""--- BLOCK_ID: {block.key} ---
原文: {block.en_block}
原译文: {block.zh_block}
参考术语: {block_old_terms_str}
""")
                
                content_str = "\n".join(blocks_text)
                
                prompt = f"""
【待处理内容】
{content_str}

【处理逻辑 - 请严格遵守】
对于每一个 Block
- proofread_zh：输出修正后的译文。
- proofread_note：输出具体的修改原因（如：术语修正/语法优化/风格调整）。如果没有修改，请留空字符串。
- new_terms: 仅当该块中出现明确"专有名词/术语/人名/地名"且不在术语表内时才输出；否则 []。
  new_terms 每项必须是：{{'term': '英文术语', 'translation': '中文译名', 'note': '可选备注'}}

【输出格式】
必须输出一个纯 JSON 列表，不要包含 Markdown 标记。
[{{
  "BLOCK_ID": "保持原样",
  "proofread_zh": "修正后的译文 或 [BLOCK_ERROR]",
  "proofread_note": "语言学备注 或 错误原因",
  "new_terms": []
}}]
"""
                
                # 记录完整的 prompt 内容
                logger.info(f"构建的完整 prompt: {prompt}")
                
                # 发送请求
                response = self.llm_engine.request_prompt(prompt=prompt, system_prompt=system_prompt)
                
                # 清理 markdown 标记
                json_str = re.sub(r'^```[jJ]son\s*', '', response.strip())
                json_str = re.sub(r'\s*```$', '', json_str)
                
                # 解析 JSON
                result_data = json.loads(json_str)
                
                # 处理返回结果
                if isinstance(result_data, list):
                    # 创建块映射，方便查找
                    block_map = {block.key: block for block in batch}
                    
                    for item in result_data:
                        block_id = item.get("BLOCK_ID")
                        if block_id and block_id in block_map:
                            block = block_map[block_id]
                            block.proofread1_zh = item.get("proofread_zh", "")
                            block.proofread1_note = item.get("proofread_note", "")
                            # 处理新术语
                            new_terms = item.get("new_terms", [])
                            if isinstance(new_terms, list):
                                block.new_terms = new_terms
                                # 将新术语添加到术语表
                                for term_data in new_terms:
                                    term = term_data.get("term", "").strip()
                                    translation = term_data.get("translation", "").strip()
                                    note = term_data.get("note", "").strip()
                                    if term and translation:
                                        # 检查是否已存在
                                        existing_terms = [t for t in self.new_terms.terms if t.term == term]
                                        if not existing_terms:
                                            self.new_terms.terms.append(TermEntry(
                                                term=term,
                                                translation=translation,
                                                note=note
                                            ))
                                # 重新构建 matcher
                                self.new_terms._build_matchers()
                            block.stage = 1  # 标记完成一校
                    
                    return batch
                else:
                    raise ValueError("返回的结果不是 JSON 列表")
                
            except Exception as e:
                # 致命错误直接熔断
                if any(x in str(e) for x in ["HTTP 401", "HTTP 403", "insufficient_quota", "鉴权", "apiKey"]):
                    raise
                
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"[Depth={depth}] 重试 {attempt+1}/{MAX_RETRIES}: {e}")
                    time.sleep(2)
                else:
                    logger.error(f"[Depth={depth}] 所有重试失败: {e}")
        
        # 拆分阶段：只有当重试彻底失败才会走到这里
        if len(batch) > 1:
            mid = len(batch) // 2
            left, right = batch[:mid], batch[mid:]
            logger.info(f"[Depth={depth}] 批次拆分: {len(left)} + {len(right)}")
            return self._process_recursive(left, depth + 1) + self._process_recursive(right, depth + 1)
        
        # 单条失败：标记为错误
        block = batch[0]
        logger.error(f"[Depth={depth}] 单条失败: {block.key}")
        block.proofread1_note = "[SYSTEM] Processing failed after max retries"
        block.proofread1_zh = "[AI_ERROR]"
        block.stage = 1  # 标记为已处理（错误）
        
        return batch
    


    