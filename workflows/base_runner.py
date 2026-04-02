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
        
        # 分批次执行
        for i in range(0, total, self.max_workers):
            batch = batches[i:i+self.max_workers]
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                futures = {}
                # 关键修改：即使在并发内部，也交错启动请求，防止瞬间并发冲垮 API
                for idx, b in enumerate(batch):
                    futures[executor.submit(func, b)] = idx
                    if self.delay_seconds > 0 and idx < len(batch) - 1:
                        logger.info(f"并发启动交错间隔，等待 {self.delay_seconds} 秒...")
                        time.sleep(self.delay_seconds)
                
                for future in as_completed(futures):
                    try:
                        data = future.result()
                        results.append(data)
                    except Exception as e:
                        logger.error(f"并发任务执行失败: {e}", exc_info=True)
                        for f in futures:
                            f.cancel()
                        if on_error:
                            on_error(e)
                        raise WorkflowError(e)
                    completed += 1
                    if on_progress:
                        on_progress(completed, total)
            
            # 整个批次完成后等待，除了最后一批
            if self.delay_seconds and i + self.max_workers < total:
                logger.info(f"批次执行完毕，冷却等待 {self.delay_seconds} 秒...")
                time.sleep(self.delay_seconds)
                
        if on_complete:
            on_complete()
        return results