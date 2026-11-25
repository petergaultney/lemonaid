"""A lemon's docs mode: `classic`, the always-loaded docs, or `packages`.

`lemon start --docs` and `place open --docs` hand a lemon's harness its mode in
`LEMONAID_DOCS`, which the harness's hooks inherit. The `SessionStart` hook records
each session's mode, so a resume started without the variable keeps it.

A session that has neither, such as a fork of another, gets `[docs] mode`. That matches
what a Claude fork loads: its launch, not its source's, decides its system prompt.

`packages` needs `[docs] roots`; without them a lemon gets `classic`, and the fallback
is logged.
"""

from pathlib import Path

from .. import docs_config
from ..config import Config
from ..docs_config import DocsConfig
from ..log import get_logger
from . import paths

ENV = "LEMONAID_DOCS"

_log = get_logger("docs.mode")


def usable(mode: str, config: DocsConfig) -> str:
    """*mode*, or `classic` when *config* can't give a lemon *mode*."""
    if mode != "packages" or config.roots:
        return mode

    _log.warning("docs mode packages needs [docs] roots; using classic")
    return "classic"


def classic_root(config: Config) -> Path | None:
    """`[docs] classic`, or the older `[codex] context_doc` when that is unset."""
    return config.docs.classic or config.codex.context_doc


def _recorded(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""
    except OSError as e:
        _log.warning("could not read %s: %s", path, e)
        return ""


def current(harness: str, session: str, launched: str, config: DocsConfig) -> str:
    """*session*'s mode: *launched* (its `LEMONAID_DOCS`), else the one recorded when it
    last started, else `[docs] mode`."""
    mode = launched or (_recorded(paths.session_mode(harness, session)) if session else "")
    if mode and mode not in docs_config.MODES:
        _log.warning(
            "unknown docs mode %r for %s-%s; using %s", mode, harness, session, config.mode
        )
        mode = ""
    return usable(mode or config.mode, config)


def session_mode(harness: str, session: str, launched: str, config: DocsConfig) -> str:
    """*session*'s `current` mode, recorded for its next start."""
    mode = current(harness, session, launched, config)
    if session:
        path = paths.session_mode(harness, session)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(mode)
        except OSError as e:
            _log.warning("could not record docs mode for %s-%s: %s", harness, session, e)

    return mode
