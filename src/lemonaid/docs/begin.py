"""A session's start: begin its context window, and give it the docs of its packages.

A Claude lemon launched with its packages in its system prompt (`start`) counts them as
given, in every window, since no compaction removes them. Any other package doc is
delivered now: all of them in Codex, and what fits in Claude, the rest at its next tool
calls. A doc changed since it was given is delivered again when a window begins.
"""

import os
from collections import abc
from pathlib import Path

from ..config import Config
from ..hooks import context_docs
from ..log import get_logger
from . import compose, frontmatter, index, lemons, mode, offers, paths, start, window

_log = get_logger("docs.begin")

_NEW_PROCESS = ("startup", "resume")  # a Claude start whose system prompt is only its launch's


def _launched(manifest: abc.Mapping) -> dict[str, dict]:
    """The docs a Claude lemon's start manifest says are in its system prompt."""
    docs = manifest.get("docs")
    if not isinstance(docs, dict):
        return {}

    return {
        key: entry for key, entry in docs.items() if isinstance(entry, dict) and "mtime" in entry
    }


def _launch_lines(docs: abc.Mapping[str, dict], base: dict) -> list[dict]:
    return [
        {
            **base,
            "kind": "doc",
            "doc": key.removesuffix("#"),
            "section": "",
            "package": entry.get("package", ""),
            "delivery": "launch",
            "chars": 0,
            "shadow": False,
        }
        for key, entry in docs.items()
    ]


def _changed(state: dict, doc: frontmatter.Doc, shadow: bool) -> bool:
    """Whether *doc* is missing from the window, or changed since it was given."""
    given = state[window.ledger(shadow)].get(f"{doc.path}#")
    try:
        return not isinstance(given, dict) or given.get("mtime") != doc.path.stat().st_mtime
    except OSError:
        return False


def _classic_fallback(harness: str, docs_mode: str, given: compose.Given, config: Config) -> str:
    """The always-loaded docs, for a Codex `packages` lemon that no package is for."""
    root = mode.classic_root(config)
    if harness != "codex" or docs_mode != "packages" or given.texts or not root:
        return ""

    _log.warning("no package is for this packages lemon; giving it the classic docs")
    return context_docs.expand(root)


def session(data: dict, harness: str, config: Config, base: dict) -> compose.Outcome:
    docs = index.build(config.docs.roots, paths.index())
    cwd = Path(data.get("cwd") or os.getcwd())
    brief_text = lemons.attached_brief(harness, base["session"])
    facts = {
        "cwd": str(cwd),
        "on_default_branch": lemons.on_default_branch(config.docs.default_branch_check, cwd),
    }
    lemon = lemons.Lemon(
        cwd, brief_text, facts["on_default_branch"], *lemons.kin(lemons.lemon_id(brief_text))
    )
    source = str(data.get("source") or "startup")
    manifest = start.claim(base["session"], source) if harness == "claude" else {}
    launched = _launched(manifest)
    with window.opened(harness, base["session"]) as state:
        if harness == "claude" and source not in _NEW_PROCESS and state["mode"]:
            base = {**base, "mode": state["mode"]}  # its process keeps the docs it loaded
        chosen = offers.packages(docs, lemon, base["mode"])
        if launched or (harness == "claude" and source in _NEW_PROCESS):
            state["prompt"] = {key: entry["mtime"] for key, entry in launched.items()}
        began = window.begin(state, source, base["mode"], chosen.given + chosen.shadow)
        if began:
            state["lemon"] = facts
        base = {**base, "window": state["window"]}
        given = compose.compose(
            state,
            base,
            offers.members(
                docs, chosen, lambda doc, shadow: began and _changed(state, doc, shadow)
            ),
            compose.limit(harness),
        )
    fallback = _classic_fallback(harness, base["mode"], given, config) if began else ""
    window_line = {
        **base,
        "kind": "window",
        "source": source,
        "cwd": str(cwd),
        "packages": state["packages"],
        "shadow": not chosen.given,
    }
    return compose.Outcome(
        [window_line, *(_launch_lines(launched, base) if began else []), *given.entries],
        "\n\n".join(t for t in (fallback, given.context()) if t),
    )
