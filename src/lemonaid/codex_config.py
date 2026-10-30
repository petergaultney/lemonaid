"""The `[codex]` table: a document lemonaid hands every Codex session at start."""

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodexConfig:
    context_doc: Path | None = None  # injected with its `@` imports; None injects nothing


def _context_doc(raw: object) -> Path | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        print(f"Warning: [codex] context_doc must be a file path, not {raw!r}", file=sys.stderr)
        return None

    try:
        return Path(raw).expanduser()
    except RuntimeError as e:
        print(f"Warning: [codex] context_doc: {e}", file=sys.stderr)
        return None


def parse(data: dict) -> CodexConfig:
    return CodexConfig(context_doc=_context_doc(data.get("context_doc")))
