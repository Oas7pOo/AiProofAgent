import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, Optional
import logging

logger = logging.getLogger("AiProofAgent.Workflow")

class WorkflowError(Exception):
    pass

class BatchTaskRunner:
    def __init__(self, max_workers=1, delay_seconds=0):
        self.max_workers = max_workers
        self.delay_seconds = delay_seconds

    def run_sync(self, batches: List[Any], func: Callable[[Any], Any], on_progress=None, on_complete=None, on_error=None):
        return self._run(batches, func, on_progress, on_complete, on_error)

    def run_async(self, batches, func, on_progress=None, on_complete=None, on_error=None):
        thread = threading.Thread(
            target=self._run,
            args=(batches, func, on_progress, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return thread

    def _run(self, batches, func, on_progress=None, on_complete=None, on_error=None):
        total = len(batches)
        if total == 0:
            if on_complete:
                on_complete()
            return []

        results = []
        completed = 0
        
        # 分批次执行，每个批次完成后等待delay_seconds
        for i in range(0, total, self.max_workers):
            batch = batches[i:i+self.max_workers]
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                futures = {executor.submit(func, b): i for i,b in enumerate(batch)}
                for future in as_completed(futures):
                    try:
                        data = future.result()
                        results.append(data)
                    except Exception as e:
                        logger.error(f"并发任务执行失败: {e}", exc_info=True)
                        # 发生致命错误时，立即取消尚未开始的排队任务
                        for f in futures:
                            f.cancel()
                        if on_error:
                            on_error(e)
                        raise WorkflowError(e)
                    completed += 1
                    if on_progress:
                        on_progress(completed, total)
            
            # 批次完成后等待delay_seconds，除了最后一批
            if self.delay_seconds and i + self.max_workers < total:
                logger.info(f"批次完成，等待 {self.delay_seconds} 秒后执行下一批次")
                time.sleep(self.delay_seconds)
                
        if on_complete:
            on_complete()
        return results
