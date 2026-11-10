"""The `[restore]` table: how `lemonaid restore` brings lost lemons back."""

import sys
from dataclasses import dataclass

AUTO = ("off", "ask", "on")


@dataclass(frozen=True)
class RestoreConfig:
    parallel: int = 4  # lemons started at once; each batch is verified before the next
    verify_seconds: float = 60.0  # how long a started lemon has to show up running in its pane
    auto: str = "ask"  # what a new server with lost lemons does: nothing, an inbox row, or restore


def _positive(key: str, raw: object, default: float, kind: type) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw <= 0:
        print(f"Warning: [restore] {key} must be a positive number", file=sys.stderr)
        return default

    return kind(raw)


def _auto(raw: object) -> str:
    if raw not in AUTO:
        print(f"Warning: [restore] auto must be one of {', '.join(AUTO)}", file=sys.stderr)
        return RestoreConfig.auto

    return str(raw)


def parse(data: dict) -> RestoreConfig:
    return RestoreConfig(
        parallel=int(_positive("parallel", data.get("parallel", 4), 4, int)),
        verify_seconds=_positive(
            "verify_seconds", data.get("verify_seconds", 60.0), RestoreConfig.verify_seconds, float
        ),
        auto=_auto(data.get("auto", RestoreConfig.auto)),
    )
