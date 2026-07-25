"""A harness for the parts of the environment replay cannot control by itself.

Replay removes non-determinism from the model and the tools. It cannot remove it
from the *agent's own code* - a `uuid4()` in a prompt, a `datetime.now()` in a
branch, a `random.choice()` in a retry policy.

This module freezes those, so "deterministic replay" is a claim that survives
contact with real agent code rather than a hopeful description.

    with deterministic(frozen_time="2026-07-25T09:00:00Z"):
        observed = replay_run(golden, agent)
"""

from __future__ import annotations

import random
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from unittest import mock

DEFAULT_FROZEN_TIME = "2026-01-01T00:00:00+00:00"
DEFAULT_SEED = 0


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class DeterministicUUID:
    """Reproducible stand-in for `uuid.uuid4`."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def __call__(self) -> uuid.UUID:
        return uuid.UUID(int=self._random.getrandbits(128), version=4)


@contextmanager
def deterministic(
    *,
    seed: int = DEFAULT_SEED,
    frozen_time: str | None = DEFAULT_FROZEN_TIME,
    patch_uuid: bool = True,
) -> Iterator[datetime]:
    """Freeze clocks, seed randomness, and make UUIDs reproducible.

    Yields the frozen instant. Patching is scoped to the block and unwound on
    exit, including on exception.

    This patches the `time`, `random`, and `uuid` module functions. Code holding
    a private reference (`from time import time`) captured before entry keeps the
    real function - a limitation worth knowing rather than pretending away.
    """
    moment = _parse(frozen_time) if frozen_time else datetime.now(timezone.utc)
    epoch = moment.timestamp()

    state = random.getstate()
    random.seed(seed)

    with ExitStack() as stack:
        if frozen_time is not None:
            stack.enter_context(mock.patch.object(time, "time", lambda: epoch))
            stack.enter_context(mock.patch.object(time, "monotonic", lambda: epoch))
            stack.enter_context(mock.patch.object(time, "perf_counter", lambda: epoch))
        if patch_uuid:
            stack.enter_context(mock.patch.object(uuid, "uuid4", DeterministicUUID(seed)))
        try:
            yield moment
        finally:
            random.setstate(state)
