"""The `[docs]` table: which docs a lemon loads, at session start and on its actions."""

import sys
from dataclasses import dataclass
from pathlib import Path

MODES = ("classic", "packages")


@dataclass(frozen=True)
class DocsConfig:
    mode: str = "classic"  # for a lemon started without `--docs`
    classic: Path | None = None  # the doc whose `@` imports are the always-loaded docs
    roots: tuple[Path, ...] = ()  # folders whose docs declare packages and triggers
    default_branch_check: str = ""  # shell command: exit 0 when the cwd is on its default branch


def _mode(raw: object) -> str:
    if raw is None:
        return "classic"
    if isinstance(raw, str) and raw in MODES:
        return raw

    print(f"Warning: [docs] mode must be one of {', '.join(MODES)}, not {raw!r}", file=sys.stderr)
    return "classic"


def _path(key: str, raw: object) -> Path | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        print(f"Warning: [docs] {key} must be a path, not {raw!r}", file=sys.stderr)
        return None

    try:
        return Path(raw).expanduser()
    except RuntimeError as e:
        print(f"Warning: [docs] {key}: {e}", file=sys.stderr)
        return None


def _roots(raw: object) -> tuple[Path, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        print(f"Warning: [docs] roots must be a list of folders, not {raw!r}", file=sys.stderr)
        return ()

    return tuple(path for item in raw if (path := _path("roots", item)))


def _command(raw: object) -> str:
    if raw is None or isinstance(raw, str):
        return raw or ""

    print(
        f"Warning: [docs] default-branch-check must be a shell command, not {raw!r}",
        file=sys.stderr,
    )
    return ""


def parse(data: dict) -> DocsConfig:
    return DocsConfig(
        mode=_mode(data.get("mode")),
        classic=_path("classic", data.get("classic")),
        roots=_roots(data.get("roots")),
        default_branch_check=_command(data.get("default-branch-check")),
    )
