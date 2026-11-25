"""A lemon's docs mode: `classic`, the always-loaded docs, or `packages`.

`lemon start --docs` and `place open --docs` hand a lemon's harness its mode in
`LEMONAID_DOCS`, which the harness's hooks inherit. The `SessionStart` hook records it
for the session, and from then on the record decides: `lemonaid docs mode` changes it,
and a session's later starts (a compaction, a resume) take it, whatever the variable says.

A session that has neither, such as a fork of another, gets `[docs] mode`. That matches
what a Claude fork loads: its launch, not its source's, decides its system prompt.

`packages` needs `[docs] roots`; without them a lemon gets `classic`, and the fallback
is logged. The record keeps the mode asked for, so restoring the roots restores it.
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


def _known(mode: str, harness: str, session: str) -> str:
    if mode in ("", *docs_config.MODES):
        return mode

    _log.warning("unknown docs mode %r for %s-%s; ignoring it", mode, harness, session)
    return ""


def wanted(harness: str, session: str, launched: str) -> str:
    """The mode recorded for *session*, else *launched* (its `LEMONAID_DOCS`); "" for
    neither."""
    recorded = _recorded(paths.session_mode(harness, session)) if session else ""
    return _known(recorded, harness, session) or _known(launched, harness, session)


def current(harness: str, session: str, launched: str, config: DocsConfig) -> str:
    """The mode *session* runs in: the one it `wanted`, else `[docs] mode`, as `usable`."""
    return usable(wanted(harness, session, launched) or config.mode, config)


def _began_path(harness: str, session: str) -> Path:
    return paths.session_mode(harness, session).with_suffix(".began")


def record(harness: str, session: str, mode: str) -> None:
    """Make *mode* the one *session* takes at its next start.

    A session started before lemonaid noted the mode each start began in has only this
    record, which then held the mode it runs in; that is kept as its start's (`began`).

    Raises OSError when it can't be written.
    """
    path, started = paths.session_mode(harness, session), _began_path(harness, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not started.exists() and (running := _recorded(path)):
        started.write_text(running)
    path.write_text(mode)


def session_mode(harness: str, session: str, launched: str, config: DocsConfig) -> str:
    """*session*'s `current` mode, with the mode it asked for recorded for its next start."""
    if session:
        try:
            record(harness, session, wanted(harness, session, launched) or config.mode)
        except OSError as e:
            _log.warning("could not record docs mode for %s-%s: %s", harness, session, e)

    return current(harness, session, launched, config)


def began(harness: str, session: str, mode: str) -> str:
    """Record that *session* starts in *mode*; the mode it last started in, "" for none.

    Raises OSError when it can't be written.
    """
    path = _began_path(harness, session)
    before = _recorded(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode)
    return before
