import json
import re
import threading
import logging
import time
from typing import List, Tuple, Dict, Callable, Optional

from core.llm_engine import LlmEngine
from core.format_converter import FormatConverter
from core.term_manager import TermManager
from core.utils import match_terms_for_block, format_terms
from models.term import TermEntry
from models.document import TranslationBlock
from workflows.base_runner import BatchTaskRunner


logger = logging.getLogger("AiProofAgent.Proofread2")

class Proofread2Workflow:
    """
    二校业务编排层 (支持交互式人工校验与自动断点)
    """
    def __init__(self, config_path="config.yaml", max_workers=None, delay_seconds=None, max_blocks=None, max_chars=None):
        from utils.config import ConfigManager
        cfg = ConfigManager(config_path)
        
        # 智能读取：同时查找嵌套格式和扁平格式
        def _get_val(keys, default):
            for k in keys:
                v = cfg.get(k)
                if v is not None and str(v).strip() != "":
                    return v
            return default
        
        # 使用外部传入的参数，如果没有则从配置文件读取
        self.max_workers = max_workers if max_workers is not None else int(_get_val(["ai_max_workers", "llm.ai_max_workers"], 1))
        self.delay_seconds = delay_seconds if delay_seconds is not None else int(_get_val(["time_wait", "llm.time_wait"], 10))
        self.max_blocks = max_blocks if max_blocks is not None else int(_get_val(["max_blocks", "llm.max_blocks"], 10))
        self.max_chars = max_chars if max_chars is not None else int(_get_val(["max_chars", "llm.max_chars"], 8000))
        
        self.llm_engine = LlmEngine(config_path)
        self.runner = BatchTaskRunner(max_workers=self.max_workers, delay_seconds=self.delay_seconds)
        self.blocks: List[TranslationBlock] = []
        self.archive_path = ""
        self.old_terms = TermManager()
        self.new_terms = TermManager()
        self.pending_queue: List[List[TranslationBlock]] = []
        
        logger.info(f"二校流水线配置: max_workers={self.max_workers}, delay_seconds={self.delay_seconds}, max_blocks={self.max_blocks}, max_chars={self.max_chars}")

    def init_session(self, archive_path: str, stage1_path: str = "", old_terms_path: str = "", new_terms_path: str = ""):
        self.archive_path = archive_path
        
        if stage1_path:
            self.blocks = FormatConverter.load_from_file(stage1_path)
            logger.info(f"从一校结果 {stage1_path} 加载 {len(self.blocks)} 个数据块")
            
            # 确保所有块的stage设置为1（一校完成）
            for block in self.blocks:
                if block.stage < 1:
                    block.stage = 1
            
            # 如果提供了术语文件，覆盖从一校恢复的术语
            self.old_terms.load_terms(old_terms_path)
            logger.info(f"已加载旧术语表: {old_terms_path}")
            self.new_terms.load_terms(new_terms_path)
            logger.info(f"已加载新术语表: {new_terms_path}")
            
            # 保存到二校存档（此时术语已经包含用户传入的术语文件）
            FormatConverter.save_to_json(self.blocks, self.archive_path, self.old_terms, self.new_terms)
        else:
            # 从二校存档加载数据和术语
            self.blocks, old_terms_entries, new_terms_entries = FormatConverter.load_from_json(self.archive_path)
            
            # 恢复术语信息
            if old_terms_entries:
                for entry in old_terms_entries:
                    self.old_terms.terms.append(TermEntry(
                                term=entry.get("term", entry.get("en", "")),
                                translation=entry.get("translation", entry.get("zh", "")),
                                note=entry.get("note", "")
                            ))
                self.old_terms._build_matchers()
                logger.info(f"从二校存档恢复 {len(old_terms_entries)} 条旧术语")
            
            if new_terms_entries:
                for entry in new_terms_entries:
                    self.new_terms.terms.append(TermEntry(
                                term=entry.get("term", entry.get("en", "")),
                                translation=entry.get("translation", entry.get("zh", "")),
                                note=entry.get("note", "")
                            ))
                self.new_terms._build_matchers()
                logger.info(f"从二校存档恢复 {len(new_terms_entries)} 条新术语")

    def build_batches(self, max_blocks: int = 10, max_chars: int = 8000) -> int:
        """将待二校的数据分组装载至处理队列"""
        # 处理所有未二校的数据块（stage < 2），不强制要求必须经过一校
        pending = [b for b in self.blocks if b.stage < 2]
        self.pending_queue = []
        
        current_batch = []
        current_chars = 0
        
        for b in pending:
            # 计算实际会出现在 prompt 中的所有字段的字符数
            # 原文 + 原译 + 一校译文 + 一校建议
            text_len = len(b.en_block) + len(b.zh_block) + len(b.proofread1_zh) + len(b.proofread1_note)
            if current_batch and (len(current_batch) >= max_blocks or current_chars + text_len > max_chars):
                self.pending_queue.append(current_batch)
                current_batch = []
                current_chars = 0
            current_batch.append(b)
            current_chars += text_len
            
        if current_batch:
            self.pending_queue.append(current_batch)
        return len(self.pending_queue)



    def build_prompt_for_batch(self, batch: List[TranslationBlock]) -> str:
        """为当前批次构建上下文连贯的 Prompt"""

        # 构建二校 prompt
        blocks = []
        for b in batch:
            # 为每个块单独匹配术语
            block_old_hits, block_new_hits = match_terms_for_block(b, self.old_terms, self.new_terms)
            
            # 格式化术语
            block_old_terms_str = format_terms(block_old_hits)
            block_new_terms_str = format_terms(block_new_hits)
            
            blocks.append(
                f"--- BLOCK_ID: {b.key} ---\n"
                f"原文: {b.en_block}\n"
                f"原译: {b.zh_block}\n"
                f"一校译文: {b.proofread1_zh}\n"
                f"一校建议: {b.proofread1_note}\n"
                f"参考术语: {block_old_terms_str}\n"
                f"新术语建议: {block_new_terms_str}\n"
            )

        prompt = (
            "你是中文 D&D 译文二校员。你熟悉dnd的中文翻译与术语，基于当前翻译稿件与质量不好的一校给出的译文与建议做最终二校，确保术语一致、语义准确、中文自然。\n"
            "\n"
            "【术语约束】\n"
            "1) 旧术语表为最高优先级（若旧术语命中，必须使用旧术语的译名）。\n"
            "2) 新术语建议仅在旧术语未覆盖时可参考，其中可能有误。\n"
            "\n"
            "【需要二校的块】\n"
            + "\n".join(blocks)
            + "\n"
            "【输出要求】\n"
            "必须输出一个纯 JSON 列表，不要包含 Markdown。\n"
            "每个对象必须包含：BLOCK_ID / proofread_zh / proofread_note。\n"
            "proofread_zh 必须给出\"最终二校译文\"（即使与一校相同也要完整输出，如原译文与一校缺失则此处为翻译）。HTML 标签中的引号冲突必须对内部的引号进行转义。如果分段奇怪则可以合并到前一段译文，此处留空。\n"
            "proofread_note 写修改原因及文中出现的术语；如果该段合并至前段，则在这里写出合并至前段。\n"
            "\n"
            "[\n"
            "  {\"BLOCK_ID\":\"...\",\"proofread_zh\":\"...\",\"proofread_note\":\"\"}\n"
            "]\n"
        )
        return prompt

    def request_llm(self, prompt: str) -> str:
        """向 LLM 发起请求并提取 JSON"""
        system_prompt = "你是一个严谨的翻译校对助手。请只输出合法的 JSON 数组结构，不要包含 markdown 代码块标记。"
        resp = self.llm_engine.request_prompt(prompt, system_prompt=system_prompt)
        resp = re.sub(r'^```[jJ]son\s*', '', resp.strip())
        resp = re.sub(r'\s*```$', '', resp)
        return resp

    def parse_and_validate(self, batch: List[TranslationBlock], text: str) -> Tuple[bool, str, List[Dict]]:
        """校验返回的 JSON 是否格式完好且与原区块一一对应"""
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                return False, "返回的结果不是 JSON 数组", []
            if len(data) != len(batch):
                return False, f"返回的数组长度 ({len(data)}) 与请求片段数量 ({len(batch)}) 不匹配", []

            req_keys = [str(b.key) for b in batch]
            resp_keys = [str(item.get("BLOCK_ID")) for item in data]
            if set(req_keys) != set(resp_keys):
                return False, f"返回的 BLOCK_ID {resp_keys} 与请求 {req_keys} 不匹配", []

            return True, "Success", data
        except Exception as e:
            # JSON 解析失败，尝试通过正则表达式提取数据
            logger.warning(f"JSON 解析失败，尝试正则提取: {e}")
            extracted_data = self._extract_data_from_text(text, batch)
            if extracted_data:
                logger.info(f"正则提取成功，提取到 {len(extracted_data)} 条数据")
                return True, "Success (regex extracted)", extracted_data
            
            # 显示前 500 字符的 JSON 内容，帮助定位问题
            preview = text[:500] + "..." if len(text) > 500 else text
            error_msg = f"JSON 解析失败: {e}\n\n返回的 JSON 内容:\n{preview}"
            return False, error_msg, []

    def _extract_data_from_text(self, text: str, batch: List[TranslationBlock]) -> List[Dict]:
        """当 JSON 解析失败时，通过正则表达式从文本中提取数据"""
        result = []
        req_keys = [str(b.key) for b in batch]
        
        # 尝试匹配每个 BLOCK_ID 对应的数据块
        for block_id in req_keys:
            # 构建正则表达式模式，匹配该 BLOCK_ID 对应的对象
            # 匹配模式: "BLOCK_ID": "xxx" ... "proofread_zh": "..." ... "proofread_note": "..."
            pattern = r'"BLOCK_ID"\s*:\s*"' + re.escape(block_id) + r'"[^}]*"proofread_zh"\s*:\s*"([^"]*)"[^}]*"proofread_note"\s*:\s*"([^"]*)"'
            
            match = re.search(pattern, text, re.DOTALL)
            if match:
                proofread_zh = match.group(1)
                proofread_note = match.group(2)
                result.append({
                    "BLOCK_ID": block_id,
                    "proofread_zh": proofread_zh,
                    "proofread_note": proofread_note
                })
        
        # 如果正则提取的数据数量与请求的不一致，返回空列表表示失败
        if len(result) != len(batch):
            return []
        
        return result

    def apply_batch(self, batch: List[TranslationBlock], data: List[Dict], save: bool = True):
        """将用户或 LLM 生成的校验数据应用到内存模型并持久化"""
        data_map = {str(item.get("BLOCK_ID")): item for item in data}
        for b in batch:
            res = data_map.get(str(b.key))
            if res:
                b.proofread_zh = res.get("proofread_zh", "")
                b.proofread_note = res.get("proofread_note", "")
                b.stage = 2
        
        if save:
            FormatConverter.save_to_json(self.blocks, self.archive_path, self.old_terms, self.new_terms)

    def run_bulk_async(self, progress_callback=None, done_callback=None, error_callback=None):
        """批量盲跑模式 (兼容之前的批处理并发逻辑)"""
        def _task():
            try:
                # 构建批次
                batch_count = self.build_batches(max_blocks=self.max_blocks, max_chars=self.max_chars)
                logger.info(f"二校流水线: 共 {len(self.blocks)} 个片段，需处理 {len([b for b in self.blocks if b.stage == 1])} 个片段，已分为 {batch_count} 个批次")
                
                if not self.pending_queue:
                    logger.info("二校流水线: 没有待处理的片段")
                    if done_callback:
                        done_callback(self.blocks)
                    return
                
                # 总块数
                total_blocks = len([b for b in self.blocks if b.stage == 1])
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
                    logger.info(f"二校进度: {completed_blocks}/{total_blocks}")
                
                # 执行并发处理
                self.runner.run_sync(self.pending_queue, self._process_batch, on_progress=custom_progress_callback)
                
                # 任务完成
                logger.info("二校流水线全部完成")
                if done_callback:
                    done_callback(self.blocks)
                    
            except Exception as e:
                logger.error(f"二校流水线发生致命错误: {e}", exc_info=True)
                if error_callback:
                    error_callback(e)
        threading.Thread(target=_task, daemon=True).start()

    def _process_batch(self, batch: List[TranslationBlock]) -> List[TranslationBlock]:
        """处理一个批次的块，包含失败重试和任务拆分机制"""
        logger.info(f"[DEBUG] _process_batch开始，批次大小={len(batch)}")
        result = self._process_recursive(batch, depth=0)
        logger.info(f"[DEBUG] _process_recursive完成，开始保存状态")
        # 处理完一个批次后保存状态
        FormatConverter.save_to_json(self.blocks, self.archive_path, self.old_terms, self.new_terms)
        logger.info(f"[DEBUG] 状态保存完成")
        logger.info(f"已保存批次处理状态到: {self.archive_path}")
        return result

    def _process_recursive(self, batch: List[TranslationBlock], depth: int = 0) -> List[TranslationBlock]:
        if not batch:
            return batch
        
        MAX_RETRIES = 3
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"[DEBUG] [Depth={depth}] 开始构建prompt")
                prompt = self.build_prompt_for_batch(batch)
                logger.info(f"[DEBUG] [Depth={depth}] prompt构建完成，长度={len(prompt)}")
                
                logger.info(f"[DEBUG] [Depth={depth}] 开始request_llm")
                response = self.request_llm(prompt)
                logger.info(f"[DEBUG] [Depth={depth}] request_llm完成，响应长度={len(response)}")
                
                logger.info(f"[DEBUG] [Depth={depth}] 开始parse_and_validate")
                valid, msg, data = self.parse_and_validate(batch, response)
                logger.info(f"[DEBUG] [Depth={depth}] parse_and_validate完成，valid={valid}")
                
                if not valid:
                    # 验证失败也视为一种需要重试的错误
                    raise ValueError(f"AI返回数据验证失败: {msg}")
                
                logger.info(f"[DEBUG] [Depth={depth}] 开始apply_batch")
                self.apply_batch(batch, data)
                logger.info(f"[DEBUG] [Depth={depth}] apply_batch完成")
                return batch
                
            except Exception as e:
                logger.error(f"[DEBUG] [Depth={depth}] 异常: {e}")
                if any(x in str(e) for x in ["HTTP 401", "HTTP 403", "insufficient_quota", "鉴权", "apiKey"]):
                    raise
                
                if attempt < MAX_RETRIES - 1:
                    # 关键修改：重试等待时间使用配置值
                    retry_wait = self.runner.delay_seconds if self.runner.delay_seconds > 0 else 2
                    logger.warning(f"[Depth={depth}] 二校请求失败，{retry_wait} 秒后重试: {e}")
                    time.sleep(retry_wait)
                else:
                    logger.error(f"[Depth={depth}] 二校重试失败: {e}")
        
        # 拆分阶段：只有当重试彻底失败才会走到这里
        if len(batch) > 1:
            mid = len(batch) // 2
            left, right = batch[:mid], batch[mid:]
            logger.info(f"[Depth={depth}] 批次拆分: {len(left)} + {len(right)}")
            return self._process_recursive(left, depth + 1) + self._process_recursive(right, depth + 1)
        
        # 单条失败：标记为错误
        block = batch[0]
        logger.error(f"[Depth={depth}] 单条失败: {block.key}")
        block.proofread_note = "[SYSTEM] Processing failed after max retries"
        block.proofread_zh = "[AI_ERROR]"
        block.stage = 2  # 标记为已处理（错误）
        
        return batch
