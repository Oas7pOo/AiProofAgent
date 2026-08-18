import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, Optional
import logging

logger = logging.getLogger("AiProofAgent.Workflow")

class WorkflowError(Exception):
    pass

class RateLimiter:
    """协调所有工作线程的请求起始间隔和各线程的响应后冷却。"""

    def __init__(self, delay_seconds, clock=None, sleeper=None, random_delay=None):
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.last_request_time = None
        self.lock = threading.Lock()
        self._thread_state = threading.local()
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._random_delay = random_delay or self._get_random_delay

    def _get_random_delay(self):
        return random.uniform(0, self.delay_seconds)

    def acquire(self):
        """等待本线程与全部线程的发送条件满足，并登记本次请求开始。"""
        start_jitter = self._random_delay()
        response_ready_at = getattr(self._thread_state, "response_ready_at", 0.0)

        while True:
            with self.lock:
                now = self._clock()
                global_ready_at = now
                if self.last_request_time is not None:
                    global_ready_at = (
                        self.last_request_time
                        + self.delay_seconds
                        + start_jitter
                    )

                ready_at = max(global_ready_at, response_ready_at)
                wait_time = ready_at - now
                if wait_time <= 0:
                    self.last_request_time = now
                    self._thread_state.response_ready_at = 0.0
                    return

            logger.info("请求限速：等待 %.2f 秒后发送...", wait_time)
            self._sleeper(wait_time)

    def mark_response_processed(self):
        """登记本线程已完成响应处理，限制该线程下一次请求的最早时间。"""
        response_jitter = self._random_delay()
        response_ready_at = self._clock() + response_jitter
        self._thread_state.response_ready_at = response_ready_at
        logger.info("响应处理完成：本线程响应后冷却 %.2f 秒...", response_jitter)

class BatchTaskRunner:
    def __init__(self, max_workers=1, delay_seconds=0):
        self.max_workers = max_workers
        self.delay_seconds = delay_seconds
        self.rate_limiter = RateLimiter(delay_seconds)

    def run_sync(self, batches: List[Any], func: Callable[[Any, RateLimiter], Any], on_progress=None, on_complete=None, on_error=None):
        return self._run(batches, func, on_progress, on_complete, on_error)

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
            
        if on_complete:
            on_complete()
        return results
