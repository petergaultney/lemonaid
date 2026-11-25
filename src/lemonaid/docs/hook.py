"""`lemonaid hooks docs`: give a lemon the docs its packages and triggers call for, and
log each delivery in `doc-deliveries.jsonl` (see `deliveries`). Without `[docs] roots`
it does nothing.

- SessionStart rebuilds the index and begins a context window, unless the session
  resumes its last one. A Claude lemon launched with its packages in its system prompt
  (`start`) counts them as given. Any other package doc is delivered now: all of them
  in Codex, and what fits in Claude.
- PreToolUse matches `command` and `edit` triggers, and `create` for a Codex patch. It
  also delivers any doc new to one of the lemon's packages, and any package the lemon
  has newly joined, so a rule added mid-session reaches lemons already running.
- PostToolUse matches `create` for a Claude `Write`, whose result says if it made the file.
- UserPromptSubmit matches `prompt` triggers.

What a lemon's mode doesn't deliver is logged as `shadow` (see `offers`). A subagent's
tool calls are skipped: they go to its own context, not the lemon's.
"""

import datetime
import json
import os
import sys
from collections import abc
from pathlib import Path

from ..config import Config, load_config
from ..hooks import tool_calls
from ..log import get_logger
from . import begin, compose, deliveries, index, lemons, mode, offers, paths, triggers, window

_log = get_logger("docs.hook")

INDEX_MAX_AGE = 60.0  # seconds a tool call trusts the index before rebuilding it


def _lemon(harness: str, session: str, facts: abc.Mapping, cwd: Path) -> lemons.Lemon:
    """The lemon now: its brief, groups and lineage read afresh, and the rest as its
    session start found them, so the default-branch check runs once per window."""
    text = lemons.attached_brief(harness, session)
    found_groups, ancestors = lemons.kin(lemons.lemon_id(text))
    return lemons.Lemon(
        Path(facts.get("cwd") or cwd),
        text,
        facts.get("on_default_branch"),
        found_groups,
        ancestors,
    )


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


def _act(data: dict, harness: str, config: Config, base: dict) -> compose.Outcome:
    pre = data.get("hook_event_name") == "PreToolUse"
    docs = (
        index.recent(config.docs.roots, paths.index(), INDEX_MAX_AGE)
        if pre
        else index.read(paths.index())
    )
    action = _action(data, harness)
    with window.opened(harness, base["session"]) as state:
        lemon = _lemon(harness, base["session"], state["lemon"], Path(data.get("cwd") or "."))
        if pre:
            state["calls"] += 1
        base = {**base, "window": state["window"], "mode": state["mode"] or base["mode"]}
        chosen = offers.packages(docs, lemon, base["mode"]) if pre else offers.Packages((), ())
        window.joined(state, chosen.given + chosen.shadow)
        given = compose.compose(
            state,
            base,
            [
                *offers.triggered(docs, action, lemon, base["mode"], refusable=pre),
                *offers.members(
                    docs,
                    chosen,
                    lambda doc, shadow: f"{doc.path}#" not in state[window.ledger(shadow)],
                ),
            ],
            compose.limit(harness),
        )
    return compose.Outcome(given.entries, given.context(), given.refusal())


def outcome(data: dict, harness: str, config: Config) -> compose.Outcome:
    """What one hook call gives the lemon, and its log lines."""
    session, event = str(data.get("session_id") or ""), data.get("hook_event_name")
    if not session or data.get("agent_id"):
        return compose.Outcome([])

    base = {
        "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "harness": harness,
        "session": session,
        "mode": mode.current(harness, session, os.environ.get(mode.ENV, ""), config.docs),
        "event": event,
    }
    if event == "SessionStart":
        return begin.session(data, harness, config, base)

    return _act(data, harness, config, base)


def handle(harness: str) -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    config = load_config()
    if not isinstance(data, dict) or not config.docs.roots:
        return

    try:
        result = outcome(data, harness, config)
        deliveries.append(result.entries)
    except Exception:  # the hook's top level: a failure must deliver nothing
        _log.exception("docs hook failed on %s", data.get("hook_event_name"))
        return

    if result.refusal:
        print(result.refusal, file=sys.stderr)
        sys.exit(2)
    if result.context:
        event = data.get("hook_event_name")
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "additionalContext": result.context,
                    }
                }
            )
        )
