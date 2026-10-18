"""`UsageMeter` (the `done` event's usage), `PeriodicTask` and `housekeeping_work` (architecture review P4.6 #2)."""

from __future__ import annotations

import threading
from collections.abc import Iterator

from src.app.outbox_relay import HOUSEKEEPING_INTERVAL_S, PeriodicTask, housekeeping_work
from src.llm.null_provider import NullProvider
from src.llm.provider import ChatMessage, GenerationRequest, GenerationResult, StreamChunk, TokenUsage
from src.workflows.orchestrator import UsageMeter

REQUEST = GenerationRequest((ChatMessage("user", "hello"),))


class CountingLLM:
    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult("ok", TokenUsage(prompt_tokens=10, completion_tokens=3), "fake")

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        yield StreamChunk("ok", done=True)


def test_the_meter_adds_up_every_call_of_one_request() -> None:
    meter = UsageMeter(CountingLLM())

    meter.generate(REQUEST)
    meter.generate(REQUEST)

    assert meter.usage() == {"prompt_tokens": 20, "completion_tokens": 6}
    assert meter.llm_disabled is False


def test_the_meter_remembers_that_no_model_answered() -> None:
    meter = UsageMeter(NullProvider())

    meter.generate(REQUEST)

    assert meter.llm_disabled is True and meter.usage() == {"prompt_tokens": 0, "completion_tokens": 0}


def test_a_periodic_task_runs_with_the_delay_it_returns_and_stops() -> None:
    rounds: list[int] = []
    twice = threading.Event()

    def work() -> float:
        rounds.append(1)
        if len(rounds) >= 2:
            twice.set()
        return 0.01

    task = PeriodicTask("test-task", work, first_delay_s=0.01)
    task.start()
    assert twice.wait(5)
    task.stop()
    done = len(rounds)

    assert not task._thread.is_alive()  # noqa: SLF001 - the thread must have ended
    assert len(rounds) == done  # no round after stop


class Idempotency:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.calls = 0

    def purge_idempotency_records(self) -> int:
        self.calls += 1
        if self.fail:
            raise RuntimeError("database down")
        return 2


class Checkpoints:
    def __init__(self) -> None:
        self.calls = 0

    def purge_idle(self) -> int:
        self.calls += 1
        return 1


def test_housekeeping_purges_both_and_waits_an_hour() -> None:
    idempotency, checkpoints = Idempotency(fail=False), Checkpoints()

    delay = housekeeping_work(idempotency, checkpoints)()  # type: ignore[arg-type]

    assert delay == HOUSEKEEPING_INTERVAL_S and (idempotency.calls, checkpoints.calls) == (1, 1)


def test_a_failing_housekeeping_round_is_logged_and_the_task_keeps_its_hourly_pace() -> None:
    idempotency = Idempotency(fail=True)

    assert housekeeping_work(idempotency, Checkpoints())() == HOUSEKEEPING_INTERVAL_S  # type: ignore[arg-type]
    assert idempotency.calls == 1
