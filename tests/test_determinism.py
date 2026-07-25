from __future__ import annotations

import random
import time
import uuid

from agentgate.determinism import deterministic


def test_time_is_frozen() -> None:
    with deterministic(frozen_time="2026-07-25T09:00:00Z"):
        first = time.time()
        second = time.time()

    assert first == second


def test_two_runs_agree() -> None:
    def run() -> tuple[float, float, str]:
        with deterministic(seed=7):
            return time.time(), random.random(), str(uuid.uuid4())

    assert run() == run()


def test_different_seeds_diverge() -> None:
    def run(seed: int) -> float:
        with deterministic(seed=seed):
            return random.random()

    assert run(1) != run(2)


def test_patches_are_unwound() -> None:
    original = time.time
    with deterministic():
        assert time.time is not original
    assert time.time is original


def test_patches_are_unwound_after_an_exception() -> None:
    original = uuid.uuid4
    try:
        with deterministic():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert uuid.uuid4 is original


def test_global_random_state_is_restored() -> None:
    random.seed(1234)
    before = random.random()

    random.seed(1234)
    with deterministic(seed=99):
        random.random()
    after = random.random()

    assert before == after


def test_frozen_time_can_be_disabled() -> None:
    with deterministic(frozen_time=None):
        assert time.time() > 1_600_000_000
