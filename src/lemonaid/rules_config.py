"""The `[rules]` table: the pattern file end-of-turn messages are checked against, and who hears of a match."""

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RulesConfig:
    patterns: Path | None = None  # unset turns the check off
    report_to: str = ""  # a lemon `tell` can reach; unset, matches are only logged


def _string(data: dict, key: str) -> str:
    raw = data.get(key, "")
    if isinstance(raw, str):
        return raw.strip()

    print(f"Warning: [rules] {key} must be a string", file=sys.stderr)
    return ""


def parse(data: object) -> RulesConfig:
    if not isinstance(data, dict):
        print("Warning: [rules] must be a table", file=sys.stderr)
        return RulesConfig()

    patterns = _string(data, "patterns")
    return RulesConfig(
        patterns=Path(patterns).expanduser() if patterns else None,
        report_to=_string(data, "report_to"),
    )
