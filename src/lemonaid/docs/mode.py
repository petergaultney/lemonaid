"""A lemon's docs mode: `classic`, the always-loaded docs, or `packages`.

`lemon start --docs` and `place open --docs` hand a lemon's harness its mode in
`LEMONAID_DOCS`, which the harness's hooks inherit. The `SessionStart` hook records
each session's mode, so a resume started without the variable keeps it.

Lemonaid can't build packages yet, so a lemon given `packages` gets `classic`, and
the fallback is logged.
"""

from pathlib import Path

from .. import docs_config
from ..config import Config
from ..log import get_logger
from . import paths

ENV = "LEMONAID_DOCS"
_BUILT = frozenset({"classic"})

_log = get_logger("docs.mode")


def built(mode: str) -> str:
    """*mode*, or `classic` when lemonaid can't build *mode*."""
    if mode in _BUILT:
        return mode

    _log.warning("docs mode %s isn't built yet; using classic", mode)
    return "classic"


def classic_root(config: Config) -> Path | None:
    """`[docs] classic`, or the older `[codex] context_doc` when that is unset."""
    return config.docs.classic or config.codex.context_doc


def launch_environment(wanted: str) -> tuple[dict[str, str], str]:
    """The environment that gives a lemon started with `--docs` *wanted* its mode, and a
    warning when it gets another; ({}, "") without `--docs`."""
    if not wanted:
        return {}, ""

    mode = built(wanted)
    warning = f"--docs {wanted} isn't available yet; starting in {mode}" if mode != wanted else ""
    return {ENV: mode}, warning


def _recorded(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""
    except OSError as e:
        _log.warning("could not read %s: %s", path, e)
        return ""


def current(harness: str, session: str, launched: str, default: str) -> str:
    """*session*'s mode: *launched* (its `LEMONAID_DOCS`), else the one recorded when it
    last started, else *default*."""
    mode = launched or (_recorded(paths.session_mode(harness, session)) if session else "")
    if mode and mode not in docs_config.MODES:
        _log.warning("unknown docs mode %r for %s-%s; using %s", mode, harness, session, default)
        mode = ""
    return built(mode or default)


def session_mode(harness: str, session: str, launched: str, default: str) -> str:
    """*session*'s `current` mode, recorded for its next start."""
    mode = current(harness, session, launched, default)
    if session:
        path = paths.session_mode(harness, session)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(mode)
        except OSError as e:
            _log.warning("could not record docs mode for %s-%s: %s", harness, session, e)

    return mode
