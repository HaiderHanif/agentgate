"""Normalising volatile values so comparisons fail for real reasons only.

UUIDs, timestamps, and signed URLs change on every run and mean nothing. Left
alone they produce false positives, and false positives are how a CI check earns
the reputation of being flaky and gets switched off.

Normalisation is applied symmetrically - to the golden trace and the observed
run - so the comparison is apples to apples.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
ISO_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
EPOCH_RE = re.compile(r"\b1[6-9]\d{8}(?:\d{3})?\b")
HEX_ID_RE = re.compile(r"\b[0-9a-f]{32,64}\b")
SIGNED_PARAM_RE = re.compile(
    r"([?&](?:sig|signature|token|expires|x-amz-signature|se|sp|sv)=)[^&\s]+",
    re.IGNORECASE,
)

PLACEHOLDER = "<{kind}>"


class Normalizer(BaseModel):
    """Replaces volatile substrings with stable placeholders.

    Every rule is opt-out, and `custom` accepts project-specific patterns:

        Normalizer(custom={"order_id": r"ORD-\\d+"})
    """

    uuids: bool = True
    timestamps: bool = True
    epochs: bool = False
    hex_ids: bool = False
    signed_urls: bool = True
    custom: dict[str, str] = Field(default_factory=dict)

    def text(self, value: str) -> str:
        """Normalise a single string."""
        result = value
        for name, pattern in self.custom.items():
            result = re.sub(pattern, PLACEHOLDER.format(kind=name), result)
        if self.uuids:
            result = UUID_RE.sub(PLACEHOLDER.format(kind="uuid"), result)
        if self.timestamps:
            result = ISO_TIMESTAMP_RE.sub(PLACEHOLDER.format(kind="timestamp"), result)
        if self.epochs:
            result = EPOCH_RE.sub(PLACEHOLDER.format(kind="epoch"), result)
        if self.hex_ids:
            result = HEX_ID_RE.sub(PLACEHOLDER.format(kind="hex"), result)
        if self.signed_urls:
            result = SIGNED_PARAM_RE.sub(r"\1<redacted-signature>", result)
        return result

    def value(self, value: Any) -> Any:
        """Normalise recursively through dicts, lists, and strings."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: self.value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.value(item) for item in value]
        return value
