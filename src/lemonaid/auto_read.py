"""Mark a session read when its turn ends with a message the user chose to skip.

The patterns come from `[inbox] auto_read` and are anchored at the start of the
final assistant message of a completed turn. Only turn completion consults them:
a permission prompt or a question is never auto-read, and a row the user marks
unread stays unread until a later turn ends with a match.
"""

import json
import re
import sys
from collections import abc

from .log import get_logger

_log = get_logger("auto_read")


def _report(problem: str) -> None:
    # stderr, not stdout: hooks run this, and Claude reads a hook's stdout.
    print(f"Warning: {problem}", file=sys.stderr)
    _log.warning(problem)


def compile_patterns(raw: object) -> tuple[re.Pattern[str], ...]:
    """Compile the configured patterns, reporting and skipping any that are invalid."""
    if not isinstance(raw, list):
        if raw is not None:
            _report(f"[inbox] auto_read must be a list of regexes, not {type(raw).__name__}")
        return ()

    compiled = []
    for pattern in raw:
        if not isinstance(pattern, str):
            _report(f"[inbox] auto_read: ignoring non-string pattern {pattern!r}")
            continue
        try:
            compiled.append(re.compile(pattern))
        except re.error as e:
            _report(f"[inbox] auto_read: ignoring invalid regex {pattern!r}: {e}")
    return tuple(compiled)


def matching(patterns: abc.Iterable[re.Pattern[str]], final_message: str) -> re.Pattern[str] | None:
    """The first pattern matching the start of *final_message*, if any.

    An empty message never matches: a turn whose final message could not be
    found is left for the user to see.
    """
    text = final_message.lstrip()
    if not text:
        return None

    return next((pattern for pattern in patterns if pattern.match(text)), None)


def newest_first(lines: abc.Sequence[str]) -> abc.Iterator[dict]:
    """A transcript tail's entries, latest first, for a backend's `final_message`."""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield entry


def status_after_turn(
    patterns: abc.Iterable[re.Pattern[str]], channel: str, final_message: str
) -> str:
    """The inbox status for a session whose turn just ended."""
    pattern = matching(patterns, final_message)
    if pattern is None:
        return "unread"

    _log.info("auto-read: channel=%s pattern=%r", channel, pattern.pattern)
    return "read"
