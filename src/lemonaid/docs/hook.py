"""`lemonaid hooks docs`: work out which docs a lemon would be given, and log them.

This is shadow mode: nothing is delivered, and each would-be delivery is appended to
`doc-deliveries.jsonl` (see `deliveries`). Without `[docs] roots` it does nothing.

- SessionStart rebuilds the index, begins a context window unless the session resumes
  its last one, and gives the lemon the docs of each package that is for it.
- PreToolUse matches `command` and `edit` triggers, and `create` for a Codex patch.
- PostToolUse matches `create` for a Claude `Write`, whose result says if it made the file.
- UserPromptSubmit matches `prompt` triggers.

A subagent's tool calls are skipped: they go to its own context, not the lemon's.
"""

import datetime
import json
import os
import sys
from pathlib import Path

from ..config import Config, load_config
from ..hooks import tool_calls
from ..log import get_logger
from . import deliveries, frontmatter, index, lemons, mode, paths, sections, triggers, window

_log = get_logger("docs.hook")


def _offer(
    state: dict, base: dict, doc: frontmatter.Doc, section: str, source: dict, before: bool
) -> dict | None:
    """The log line for giving *doc*'s *section* now, or None when this window doesn't
    need it again yet."""
    key, whole = f"{doc.path}#{section}", f"{doc.path}#"
    try:
        mtime = doc.path.stat().st_mtime
        delivery = window.delivery(state, key, mtime, bool(doc.reminder), whole, before)
        if not delivery:
            return None

        text = (
            doc.reminder if delivery == "reminder" else sections.text(doc.path.read_text(), section)
        )
    except OSError as e:
        _log.warning("could not read %s: %s", doc.path, e)
        return None

    window.given(state, key, mtime, package="package" in source)
    return {
        **base,
        "kind": "doc",
        "doc": str(doc.path),
        "section": section,
        **source,
        "delivery": delivery,
        "chars": len(text),
    }


def _start(data: dict, harness: str, config: Config, base: dict) -> list[dict]:
    docs = index.build(config.docs.roots, paths.index())
    cwd = Path(data.get("cwd") or os.getcwd())
    lemon = lemons.Lemon(
        cwd,
        lemons.attached_brief(harness, base["session"]),
        lemons.on_default_branch(config.docs.default_branch_check, cwd),
    )
    names = lemons.packages(docs, lemon)
    source = str(data.get("source") or "startup")
    with window.opened(harness, base["session"]) as state:
        began = window.begin(state, source, names)
        base = {**base, "window": state["window"]}
        return [
            {
                **base,
                "kind": "window",
                "source": source,
                "cwd": str(cwd),
                "packages": state["packages"],
            },
            *(
                entry
                for name in (names if began else [])
                for doc in docs
                if name in doc.packages
                if (entry := _offer(state, base, doc, "", {"package": name}, before=False))
            ),
        ]


def _action(data: dict, harness: str) -> triggers.Action:
    event = data.get("hook_event_name")
    if event == "UserPromptSubmit":
        return triggers.Action(prompt=str(data.get("prompt") or ""))
    if event == "PostToolUse":
        return triggers.Action(
            created=tuple(tool_calls.created(data)) if harness == "claude" else ()
        )

    return triggers.Action(
        commands=tuple(tool_calls.commands(data.get("tool_input"))),
        written=tuple(tool_calls.written(data)),
        created=tuple(tool_calls.created(data)),
    )


def _act(data: dict, harness: str, base: dict) -> list[dict]:
    docs, action = index.read(paths.index()), _action(data, harness)
    with window.opened(harness, base["session"]) as state:
        if data.get("hook_event_name") == "PreToolUse":
            state["calls"] += 1
        base = {**base, "window": state["window"]}
        return [
            entry
            for doc in docs
            for trigger in doc.triggers
            if triggers.matches(trigger, action)
            if (
                entry := _offer(
                    state,
                    base,
                    doc,
                    trigger.section,
                    {"trigger": f"{trigger.kind} {trigger.pattern}"},
                    trigger.before,
                )
            )
        ]


def entries(data: dict, harness: str, config: Config) -> list[dict]:
    """The log lines for one hook call."""
    session, event = str(data.get("session_id") or ""), data.get("hook_event_name")
    if not session or data.get("agent_id"):
        return []

    base = {
        "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "harness": harness,
        "session": session,
        "mode": mode.current(harness, session, os.environ.get(mode.ENV, ""), config.docs.mode),
        "event": event,
        "shadow": True,
    }
    return (
        _start(data, harness, config, base)
        if event == "SessionStart"
        else _act(data, harness, base)
    )


def handle(harness: str) -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    config = load_config()
    if not isinstance(data, dict) or not config.docs.roots:
        return

    try:
        deliveries.append(entries(data, harness, config))
    except Exception:  # the hook's top level: a failure must deliver nothing
        _log.exception("docs hook failed on %s", data.get("hook_event_name"))
