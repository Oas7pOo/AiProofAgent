import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from core.term_manager import TermManager
from models.document import TranslationBlock
from ui.tab_proof2 import Proof2Tab
from workflows.base_runner import RateLimiter
from workflows.proofread1_flow import Proofread1Workflow
from workflows.proofread2_flow import Proofread2Workflow


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class TrackingLimiter:
    def __init__(self):
        self.acquire_calls = 0
        self.response_processed_calls = 0

    def acquire(self):
        self.acquire_calls += 1

    def mark_response_processed(self):
        self.response_processed_calls += 1


class ValueHolder:
    def set(self, _value):
        pass


class RequestPacingTests(unittest.TestCase):
    def test_global_start_interval_includes_random_jitter(self):
        clock = FakeClock()
        delays = iter([0.0, 5.0])
        limiter = RateLimiter(
            15,
            clock=clock.time,
            sleeper=clock.sleep,
            random_delay=lambda: next(delays),
        )

        limiter.acquire()
        limiter.acquire()

        self.assertEqual(clock.sleeps, [20.0])
        self.assertEqual(limiter.last_request_time, 20.0)

    def test_response_cooldown_applies_to_the_same_thread(self):
        clock = FakeClock()
        delays = iter([0.0, 10.0, 0.0])
        limiter = RateLimiter(
            15,
            clock=clock.time,
            sleeper=clock.sleep,
            random_delay=lambda: next(delays),
        )

        limiter.acquire()
        clock.now = 20.0
        limiter.mark_response_processed()
        limiter.acquire()

        self.assertEqual(clock.sleeps, [10.0])
        self.assertEqual(limiter.last_request_time, 30.0)

    def test_response_cooldown_does_not_block_another_thread(self):
        clock = FakeClock()
        delays = iter([0.0, 15.0, 0.0])
        limiter = RateLimiter(
            15,
            clock=clock.time,
            sleeper=clock.sleep,
            random_delay=lambda: next(delays),
        )

        limiter.acquire()
        clock.now = 20.0
        limiter.mark_response_processed()

        worker = threading.Thread(target=limiter.acquire)
        worker.start()
        worker.join()

        self.assertEqual(limiter.last_request_time, 20.0)
        self.assertEqual(clock.sleeps, [])

    def test_proofread1_marks_response_after_successful_parse(self):
        workflow = object.__new__(Proofread1Workflow)
        workflow.old_terms = TermManager()
        workflow.new_terms = TermManager()
        workflow.llm_engine = type(
            "LlmStub",
            (),
            {
                "request_prompt": lambda *_args, **_kwargs: (
                    '[{"BLOCK_ID":"BLOCK_001","proofread_zh":"译文",'
                    '"proofread_note":"","new_terms":[]}]'
                )
            },
        )()
        limiter = TrackingLimiter()
        block = TranslationBlock(key="block-1", en_block="source", zh_block="target")

        workflow._process_recursive([block], rate_limiter=limiter)

        self.assertEqual(limiter.acquire_calls, 1)
        self.assertEqual(limiter.response_processed_calls, 1)
        self.assertEqual(block.stage, 1)

    def test_proofread2_marks_response_after_successful_parse(self):
        workflow = object.__new__(Proofread2Workflow)
        workflow.build_prompt_for_batch = lambda _batch: "prompt"
        workflow.request_llm = lambda _prompt: "response"
        workflow.parse_and_validate = lambda _batch, _response: (
            True,
            "Success",
            [],
        )
        workflow.apply_batch = lambda _batch, _data: None
        limiter = TrackingLimiter()

        workflow._process_recursive([object()], rate_limiter=limiter)

        self.assertEqual(limiter.acquire_calls, 1)
        self.assertEqual(limiter.response_processed_calls, 1)

    def test_proofread1_marks_response_after_each_failed_attempt(self):
        workflow = object.__new__(Proofread1Workflow)
        workflow.old_terms = TermManager()
        workflow.new_terms = TermManager()
        workflow.llm_engine = type(
            "LlmStub",
            (),
            {
                "request_prompt": lambda *_args, **_kwargs: (
                    (_ for _ in ()).throw(RuntimeError("request failed"))
                )
            },
        )()
        limiter = TrackingLimiter()
        block = TranslationBlock(key="block-1", en_block="source", zh_block="target")

        workflow._process_recursive([block], rate_limiter=limiter)

        self.assertEqual(limiter.acquire_calls, 3)
        self.assertEqual(limiter.response_processed_calls, 3)

    def test_proofread2_marks_response_after_each_failed_attempt(self):
        workflow = object.__new__(Proofread2Workflow)
        workflow.build_prompt_for_batch = lambda _batch: "prompt"
        workflow.request_llm = lambda _prompt: (
            (_ for _ in ()).throw(RuntimeError("request failed"))
        )
        limiter = TrackingLimiter()
        block = TranslationBlock(key="block-1")

        workflow._process_recursive([block], rate_limiter=limiter)

        self.assertEqual(limiter.acquire_calls, 3)
        self.assertEqual(limiter.response_processed_calls, 3)

    def test_auto_proofread_uses_the_updated_request_signature(self):
        block = TranslationBlock(key="block-1", stage=1)
        limiter = TrackingLimiter()
        workflow = SimpleNamespace(
            blocks=[block],
            build_prompt_for_batch=lambda _batch: "prompt",
            request_llm=Mock(return_value="response"),
            parse_and_validate=lambda _batch, _response: (True, "Success", []),
            apply_batch=lambda _batch, _data: setattr(block, "stage", 2),
        )
        tab = object.__new__(Proof2Tab)
        tab.workflow = workflow
        tab.rate_limiter = limiter
        tab.batch_queue = [[block]]
        tab.progress_var = ValueHolder()
        tab.after = lambda _delay, callback: callback()
        tab._set_resp_text = lambda _text: None
        tab._show_current_batch = lambda: None

        self.assertTrue(tab._auto_process_one_batch([block]))
        workflow.request_llm.assert_called_once_with("prompt")
        self.assertEqual(limiter.acquire_calls, 1)
        self.assertEqual(limiter.response_processed_calls, 1)


if __name__ == "__main__":
    unittest.main()
