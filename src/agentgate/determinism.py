"""A harness for the parts of the environment replay cannot control by itself.

Replay removes non-determinism from the model and the tools. It cannot remove it
from the *agent's own code* - a `uuid4()` in a prompt, a `datetime.now()` in a
branch, a `random.choice()` in a retry policy.

This module freezes those, so "deterministic replay" is a claim that survives
contact with real agent code rather than a hopeful description.

    with deterministic(frozen_time="2026-07-25T09:00:00Z"):
        observed = replay_run(golden, agent)

Wall clocks and elapsed clocks are treated differently, on purpose:

* `time.time`, `time.time_ns` and `datetime.now` are **frozen**. They answer
  "what is the date?", and a stable answer is the whole point.
* `time.monotonic` and `time.perf_counter` **advance** by a fixed step. They
  answer "how long has this taken?", and freezing them is a trap: code shaped
  like `while time.monotonic() - start < timeout` would never terminate. The
  sequence of values is still identical on every run, so determinism holds.
"""

from __future__ import annotations

import datetime as datetime_module
import random
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone, tzinfo
from unittest import mock

DEFAULT_FROZEN_TIME = "2026-01-01T00:00:00+00:00"
DEFAULT_SEED = 0
DEFAULT_CLOCK_STEP = 0.001


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class DeterministicUUID:
    """Reproducible stand-in for `uuid.uuid4`."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def __call__(self) -> uuid.UUID:
        return uuid.UUID(int=self._random.getrandbits(128), version=4)


class AdvancingClock:
    """An elapsed-time clock that is reproducible *and* strictly increasing.

    Deterministic without being frozen. Two runs see the same sequence of
    values, but the sequence still moves forward, so timeout and retry loops
    written against it terminate.
    """

    def __init__(self, start: float, step: float = DEFAULT_CLOCK_STEP) -> None:
        self._value = start
        self._step = step

    def __call__(self) -> float:
        self._value += self._step
        return self._value


def _frozen_datetime_class(moment: datetime) -> type[datetime]:
    """A `datetime` subclass whose `now`/`utcnow`/`today` return a fixed instant.

    Naive calls return the instant with its timezone dropped rather than
    converted to local time - converting would reintroduce the machine's
    timezone as a source of divergence, which is what we came here to remove.
    """

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return moment.astimezone(tz) if tz is not None else moment.replace(tzinfo=None)

        @classmethod
        def utcnow(cls) -> datetime:
            return moment.replace(tzinfo=None)

        @classmethod
        def today(cls) -> datetime:
            return moment.replace(tzinfo=None)

    return FrozenDateTime


@contextmanager
def deterministic(
    *,
    seed: int = DEFAULT_SEED,
    frozen_time: str | None = DEFAULT_FROZEN_TIME,
    patch_uuid: bool = True,
    patch_datetime: bool = True,
    clock_step: float = DEFAULT_CLOCK_STEP,
) -> Iterator[datetime]:
    """Freeze clocks, seed randomness, and make UUIDs reproducible.

    Yields the frozen instant. Patching is scoped to the block and unwound on
    exit, including on exception.

    This patches module attributes: `time.time`, `time.monotonic`,
    `datetime.datetime`, `uuid.uuid4`. Code holding a private reference captured
    before entry - `from datetime import datetime` at import time, then
    `datetime.now()` - keeps the real function. That is a genuine limitation of
    monkeypatching rather than something to paper over: reference the module
    (`import datetime; datetime.datetime.now()`) if you need it frozen.
    """
    moment = _parse(frozen_time) if frozen_time else datetime.now(timezone.utc)
    epoch = moment.timestamp()

    state = random.getstate()
    try:
        random.seed(seed)
        with ExitStack() as stack:
            if frozen_time is not None:
                elapsed = AdvancingClock(epoch, clock_step)
                stack.enter_context(mock.patch.object(time, "time", lambda: epoch))
                stack.enter_context(
                    mock.patch.object(time, "time_ns", lambda: int(epoch * 1_000_000_000))
                )
                stack.enter_context(mock.patch.object(time, "monotonic", elapsed))
                stack.enter_context(mock.patch.object(time, "perf_counter", elapsed))
                if patch_datetime:
                    stack.enter_context(
                        mock.patch.object(
                            datetime_module, "datetime", _frozen_datetime_class(moment)
                        )
                    )
            if patch_uuid:
                stack.enter_context(mock.patch.object(uuid, "uuid4", DeterministicUUID(seed)))
            yield moment
    finally:
        random.setstate(state)
