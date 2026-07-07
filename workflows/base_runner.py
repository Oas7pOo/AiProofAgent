import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, Optional
import logging

logger = logging.getLogger("AiProofAgent.Workflow")

class WorkflowError(Exception):
    pass

class RateLimiter:
    def __init__(self, delay_seconds):
        self.delay_seconds = delay_seconds
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def acquire(self):
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.delay_seconds:
                wait_time = self.delay_seconds - time_since_last
                logger.info(f"速率限制：等待 {wait_time:.2f} 秒...")
                time.sleep(wait_time)
            self.last_request_time = time.time()

class BatchTaskRunner:
    def __init__(self, max_workers=1, delay_seconds=0):
        self.max_workers = max_workers
        self.delay_seconds = delay_seconds
        self.rate_limiter = RateLimiter(delay_seconds)

    def run_sync(self, batches: List[Any], func: Callable[[Any, RateLimiter], Any], on_progress=None, on_complete=None, on_error=None):
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
        
        for i in range(0, total, self.max_workers):
            batch = batches[i:i+self.max_workers]
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                futures = {}
                for idx, b in enumerate(batch):
                    # 在提交任务前进行速率限制，确保任务之间有足够的间隔
                    if self.delay_seconds > 0 and idx > 0:
                        logger.info(f"速率限制：等待 {self.delay_seconds} 秒后提交下一个任务...")
                        time.sleep(self.delay_seconds)
                    futures[executor.submit(func, b, self.rate_limiter)] = idx
                
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
            
            if self.delay_seconds and i + self.max_workers < total:
                logger.info(f"批次执行完毕，冷却等待 {self.delay_seconds} 秒...")
                time.sleep(self.delay_seconds)
                
        if on_complete:
            on_complete()
        return results