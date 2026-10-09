"""How much of its context a lemon has used, against a configured threshold."""

import re
import sys
from collections import abc
from dataclasses import dataclass

_TOKENS = re.compile(r"(\d+(?:\.\d+)?)\s*([kKmM])")
_SUFFIXES = {"k": 1_000, "m": 1_000_000}


@dataclass(frozen=True)
class Threshold:
    """A point in a lemon's context, as tokens or as a share of its window.

    A share needs the harness to report the window; a token count doesn't.
    Neither set means the reading is not shown.
    """

    tokens: int = 0
    share: float = 0.0


def _parse_one(key: str, raw: object) -> Threshold | None:
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return Threshold(tokens=raw)

    text = raw.strip() if isinstance(raw, str) else ""
    if text.endswith("%") and (match := re.fullmatch(r"\d+(?:\.\d+)?", text[:-1].strip())):
        return Threshold(share=float(match.group()) / 100)

    if match := _TOKENS.fullmatch(text):
        return Threshold(tokens=int(float(match.group(1)) * _SUFFIXES[match.group(2).lower()]))

    print(f"lemonaid: [tui.context_threshold] {key}: ignoring {raw!r}", file=sys.stderr)
    return None


def parse_thresholds(raw: object) -> dict[str, Threshold]:
    """`[tui.context_threshold]`: a harness or model name to `"50%"`, `"650k"`, or tokens."""
    if not isinstance(raw, dict):
        return {}

    return {
        key: threshold
        for key, value in raw.items()
        if (threshold := _parse_one(key, value)) is not None
    }


def threshold_for(
    thresholds: abc.Mapping[str, Threshold], harness: str, model: str
) -> Threshold | None:
    """A model's own threshold, else its harness's; None when neither is configured."""
    return thresholds.get(model) or thresholds.get(harness)


def percent(used: int, window: int, threshold: Threshold) -> int | None:
    """`used` as a percentage of the threshold, or None when it can't be placed."""
    limit = threshold.tokens or int(threshold.share * window)
    if used <= 0 or limit <= 0:
        return None

    return used * 100 // limit
