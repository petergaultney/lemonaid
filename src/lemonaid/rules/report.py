"""What a match says: the report to the configured address, and the rule a `tell` pattern gives the lemon."""

import re
import subprocess
import sys
from pathlib import Path

from . import hits, rule_text, snapshot
from .patterns import Pattern

_AROUND = 150  # characters of context on each side of a match


def excerpt(text: str, found: re.Match[str]) -> str:
    """About 300 characters around *found*, the match in bold, on one line."""
    stripped = found.group(0).strip() or found.group(0)
    start = found.start() + found.group(0).find(stripped)
    end = start + len(stripped)
    first, last = max(0, start - _AROUND), min(len(text), end + _AROUND)
    marked = f"{text[first:start]}**{stripped}**{text[end:last]}"
    return f"{'...' if first else ''}{' '.join(marked.split())}{'...' if last < len(text) else ''}"


def _cited(pattern: Pattern) -> str:
    home = str(Path.home())
    path = str(pattern.rule_file)
    return f"~{path.removeprefix(home)}" if path.startswith(home + "/") else path


def body(hit: hits.Hit, pattern: Pattern, held: int) -> str:
    """The report; `tell`'s header carries the lemon's return address."""
    told = "the lemon was told the rule" if pattern.mode == "tell" else "the lemon was not told"
    return "\n".join(
        [
            f"`{pattern.id}` matched the end of a lemon's turn; its return address is this "
            "message's sender.",
            "",
            f"- Rule: the one starting {pattern.rule_starts!r} in {_cited(pattern)}",
            f"- Mode: {pattern.mode} ({told})",
            f"- Working directory: {hit.cwd or 'unknown'}",
            f"- Transcript: {hit.transcript or 'unknown'}",
            "",
            f"> {hit.excerpt}",
            *(
                [
                    "",
                    f"The hourly limit held {held} earlier match{'es' if held > 1 else ''} "
                    f"unreported; each is in {hits.path()}.",
                ]
                if held
                else []
            ),
        ]
    )


def telling(pattern: Pattern) -> str:
    """What a lemon is told when a `tell` pattern matches the message it ended its turn with."""
    rule = rule_text.read(pattern.rule_file, pattern.rule_starts)
    quoted = (
        "\n".join(f"> {line}" if line else ">" for line in rule.splitlines())
        if rule
        else f"> (the rule starting {pattern.rule_starts!r}, which is no longer there)"
    )
    return "\n".join(
        [
            f"Your final message matches `{pattern.id}`, a sign it may break this rule "
            f"from {_cited(pattern)}:",
            "",
            quoted,
            "",
            pattern.say,
            "If your message doesn't break the rule, end your turn as it was.",
        ]
    )


def send(address: str, channel: str, text: str) -> None:
    """`lemonaid tell` *address* from *channel*, detached, so delivery never holds a turn."""
    log = snapshot.rules_dir() / "tell.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as out:
        subprocess.Popen(
            [sys.executable, "-m", "lemonaid", "tell", "--channel", channel, "--", address, text],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            start_new_session=True,
        )
