"""The end-of-turn check: the message a lemon ended its turn with, against the promoted patterns.

It runs in lemonaid's Stop hook in both harnesses, whose input carries that message, and
never looks at tool calls. Every match is logged; a match is reported to `[rules]
report_to` within the limits in `hits`, and a `tell` pattern also holds the stop once
with the rule. Each search has a time limit, and all of them together a budget, so no
pattern can keep the hook from finishing. Any error is logged in one line and lets the
turn end.
"""

import re
import sqlite3
import time
import typing as ty
from collections import abc
from fnmatch import fnmatch
from pathlib import Path

from .. import brief, rules_config
from ..claude import notify, print_mode
from ..config import load_config
from ..hooks import session_brief
from ..inbox import db
from ..log import get_logger
from . import hits, report, search, snapshot
from .patterns import Pattern

_log = get_logger("rules.end_of_turn")

_CAP = 20 * 1024  # bytes read from the end of a message
_SEARCH_SECONDS = 0.5  # one pattern on one message
_BUDGET = 2.0  # every pattern on one message


class Checked(ty.NamedTuple):
    found: list[tuple[Pattern, re.Match[str]]]
    too_slow: list[Pattern]  # stopped at the time limit, or not run once the budget was spent


def capped(text: str) -> str:
    return text.encode()[-_CAP:].decode(errors="ignore")


def applies(pattern: Pattern, cwd: str) -> bool:
    return not pattern.cwd or fnmatch(cwd, str(Path(pattern.cwd).expanduser()))


def matches(patterns: abc.Iterable[Pattern], text: str, cwd: str) -> Checked:
    deadline = time.monotonic() + _BUDGET
    found, too_slow = [], []
    for pattern in patterns:
        if not applies(pattern, cwd):
            continue

        seconds = min(_SEARCH_SECONDS, deadline - time.monotonic())
        try:
            if match := search.search(pattern.regex, text, seconds):
                found.append((pattern, match))
        except search.TooSlow:
            too_slow.append(pattern)
    return Checked(found, too_slow)


def _final_message(data: dict, harness: str) -> str:
    if harness == "claude":
        return notify.final_message(data)

    said = data.get("last_assistant_message")
    return said if isinstance(said, str) else ""


def _is_report_address(conn: sqlite3.Connection, address: str, channel: str) -> bool:
    try:
        return brief.lemon.attachment(conn, address).channel == channel
    except LookupError:
        return False


def check(
    channel: str,
    harness: str,
    cwd: str,
    transcript: str,
    said: str,
    config: rules_config.RulesConfig,
    now: float,
) -> list[Pattern]:
    """Log and report what the message *said* to end a turn on *channel* matches; the `tell`
    patterns among the matches."""
    if config.patterns is None:
        return []

    patterns = snapshot.load(config.patterns)
    if not patterns:
        return []

    text = capped(said)
    found, too_slow = matches(patterns, text, cwd)
    for pattern in too_slow:
        _log.warning("skipped %s, out of time on a final message in %s", pattern.id, cwd)
    if not found:
        return []

    with db.connect() as conn:
        if config.report_to and _is_report_address(conn, config.report_to, channel):
            _log.info("not checking %s, the report address's own session", channel)
            return []

    for pattern, match in found:
        hit = hits.Hit(
            channel, pattern.id, pattern.mode, harness, cwd, transcript, report.excerpt(text, match)
        )
        outcome = hits.record(hit, now, bool(config.report_to))
        _log.info("%s matched the end of %s's turn: %s", pattern.id, channel, outcome.outcome)
        if outcome.outcome == hits.REPORTED:
            report.send(config.report_to, channel, report.body(hit, pattern, outcome.held))
    return [pattern for pattern, _ in found if pattern.mode == "tell"]


def _check(data: dict, harness: str, config: rules_config.RulesConfig, now: float) -> str:
    if config.patterns is None or (harness == "claude" and print_mode.is_print_session()):
        return ""

    told = check(
        session_brief.channel(harness, data.get("session_id")),
        harness,
        data.get("cwd") or "",
        data.get("transcript_path") or "",
        _final_message(data, harness),
        config,
        now,
    )
    return "\n\n".join(report.telling(pattern) for pattern in told)


def reason_to_block(data: dict, harness: str) -> str:
    """The rule to tell the lemon before its turn ends, or "" to tell it nothing."""
    try:
        return _check(data, harness, load_config().rules, time.time())
    except Exception as error:  # the top of the check: no fault in it may hold a turn
        _log.warning("rule check skipped: %s: %s", type(error).__name__, error)
        return ""
