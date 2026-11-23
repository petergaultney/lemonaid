"""The `[docs]` table: which docs a lemon loads when its session starts."""

import sys
from dataclasses import dataclass
from pathlib import Path

MODES = ("classic", "packages")


@dataclass(frozen=True)
class DocsConfig:
    mode: str = "classic"  # for a lemon started without `--docs`
    classic: Path | None = None  # the doc whose `@` imports are the always-loaded docs


def _mode(raw: object) -> str:
    if raw is None:
        return "classic"
    if isinstance(raw, str) and raw in MODES:
        return raw

    print(f"Warning: [docs] mode must be one of {', '.join(MODES)}, not {raw!r}", file=sys.stderr)
    return "classic"


def _classic(raw: object) -> Path | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        print(f"Warning: [docs] classic must be a file path, not {raw!r}", file=sys.stderr)
        return None

    try:
        return Path(raw).expanduser()
    except RuntimeError as e:
        print(f"Warning: [docs] classic: {e}", file=sys.stderr)
        return None


def parse(data: dict) -> DocsConfig:
    return DocsConfig(mode=_mode(data.get("mode")), classic=_classic(data.get("classic")))
