"""Configurable review-thread filters for PR watchers."""

import sys
from dataclasses import dataclass, field


@dataclass
class PrConfig:
    skip_outdated: bool = False
    skip_resolved: bool = False


@dataclass
class WatchConfig:
    pr: PrConfig = field(default_factory=PrConfig)


def parse(data: dict) -> WatchConfig:
    pr = data.get("pr", {})
    values: dict[str, bool] = {}
    for key in ("skip_outdated", "skip_resolved"):
        value = pr.get(key, False)
        if not isinstance(value, bool):
            print(f"Warning: [watch.pr] {key} must be a boolean", file=sys.stderr)
            value = False
        values[key] = value
    return WatchConfig(pr=PrConfig(**values))
