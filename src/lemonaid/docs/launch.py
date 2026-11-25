"""What `lemon start` and `place open` give a new lemon for its docs mode.

- A `packages` lemon gets the packages that are for it. A Claude lemon gets them in its
  system prompt (`start`), and `claudeMdExcludes` on `[docs] classic` turns off the
  always-loaded docs. A Codex lemon's `SessionStart` hook injects them.
- A `classic` lemon loads the always-loaded docs, plus any package for its group or its
  lead, which a Claude lemon also gets in its system prompt.

The mode is `--docs`, else the brief's `docs-mode`, else `[docs] mode`. A lemon whose
packages can't be built starts in `classic`, with a warning.
"""

from collections import abc
from dataclasses import dataclass, field
from pathlib import Path

from .. import brief, docs_config
from ..config import Config
from ..hooks import session_brief
from ..launch import command
from ..log import get_logger
from . import index, lemons, mode, paths, start

_log = get_logger("docs.launch")


@dataclass(frozen=True)
class Launch:
    environment: dict[str, str] = field(default_factory=dict)
    claude_flags: tuple[str, ...] = ()  # a Claude harness's extra arguments
    warning: str = ""


@dataclass(frozen=True)
class Kin:
    """What the launch knows of the new lemon's brief, groups and parent before its link
    is recorded."""

    brief: Path | None = None
    groups: tuple[str, ...] = ()
    parent: str = ""  # Lemon-ID


def _lemon(kin: Kin, directory: Path, config: Config) -> lemons.Lemon:
    try:
        text = kin.brief.read_text() if kin.brief else ""
    except OSError as e:
        _log.warning("could not read brief %s: %s", kin.brief, e)
        text = ""
    own_groups, own_ancestors = lemons.kin(lemons.lemon_id(text))
    parent_groups, parent_ancestors = lemons.kin(kin.parent)
    return lemons.Lemon(
        directory,
        text,
        lemons.on_default_branch(config.docs.default_branch_check, directory),
        tuple(dict.fromkeys([*kin.groups, *own_groups, *(() if kin.groups else parent_groups)])),
        (kin.parent, *parent_ancestors) if kin.parent else own_ancestors,
    )


def brief_mode(path: Path | None) -> str:
    """The `docs-mode` *path*'s frontmatter asks for; "" without one."""
    try:
        wanted = brief.frontmatter.fields(path.read_text()).get("docs-mode") if path else None
    except (OSError, ValueError) as e:
        _log.warning("could not read docs-mode from %s: %s", path, e)
        return ""
    if wanted is None or wanted in docs_config.MODES:
        return wanted or ""

    _log.warning("%s: docs-mode must be one of %s, not %r", path, docs_config.MODES, wanted)
    return ""


def _fallback(wanted: str, why: str) -> tuple[str, str]:
    _log.warning("starting a lemon in classic, not packages: %s", why)
    return "classic", f"docs mode {wanted}: {why}; starting in classic" if wanted else ""


def _claude(
    members: abc.Sequence[start.Member], chosen: str, config: Config
) -> tuple[dict[str, str], tuple[str, ...]]:
    root = mode.classic_root(config)
    settings = {"claudeMdExcludes": [str(root)]} if chosen == "packages" and root else None
    manifest, flags = start.write(members, settings)
    return {start.START_ENV: str(manifest)}, tuple(flags)


def prepare(wanted: str, directory: Path, kin: Kin, config: Config, line: str) -> Launch:
    """The docs side of launching the lemon *line* starts in *directory*, with `--docs`
    *wanted* ("" for the brief's or `[docs] mode`). Without `[docs] roots` and a mode
    asked for, it changes nothing.

    Claude takes only the last of several `--settings`, so a Claude line that passes its
    own can't also turn off the always-loaded docs, and starts in `classic`.
    """
    wanted = wanted or brief_mode(kin.brief)
    chosen, warning = wanted or config.docs.mode, ""
    claude = command.is_claude(line)
    if not config.docs.roots:
        if chosen == "packages":
            chosen, warning = _fallback(wanted, "[docs] roots is not set")
        return Launch({mode.ENV: chosen} if wanted else {}, (), warning)

    try:
        docs = index.build(config.docs.roots, paths.index())
        lemon = _lemon(kin, directory, config)
        names = lemons.packages(docs, lemon, scoped_only=chosen == "classic")
        if chosen == "packages" and not names:
            chosen, warning = _fallback(wanted, "no package is for this lemon")
        elif chosen == "packages" and claude and not mode.classic_root(config):
            chosen, warning = _fallback(
                wanted, "[docs] classic is not set, so Claude can't skip it"
            )
        elif chosen == "packages" and claude and command.passes(line, "--settings"):
            chosen, warning = _fallback(
                wanted, "its command passes --settings, which would replace lemonaid's"
            )
        if chosen == "classic":
            names = lemons.packages(docs, lemon, scoped_only=True)
        environment, flags = (
            _claude(start.members(docs, names), chosen, config) if names and claude else ({}, ())
        )
    except OSError as e:
        chosen, warning = _fallback(wanted, f"could not write its start docs: {e}")
        environment, flags = {}, ()

    changed = wanted or chosen != config.docs.mode
    return Launch({**environment, **({mode.ENV: chosen} if changed else {})}, flags, warning)


def resumed(session: str, directory: Path, config: Config, line: str) -> Launch:
    """The docs side of resuming Claude session *session* with *line*, built afresh for
    the mode it now has (`lemonaid docs mode` may have changed it) and its docs now."""
    return prepare(
        mode.wanted("claude", session, ""),
        directory,
        Kin(session_brief.attached({"session_id": session}, "claude")),
        config,
        line,
    )
