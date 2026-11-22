"""The promoted copy of a pattern file, the only patterns the end-of-turn check reads.

Only `rules check --promote` writes it, after every check passes, so a half-saved
edit to the pattern file, or a sync conflict in it, changes nothing that runs.
"""

import datetime as dt
import json
import os
from pathlib import Path

from ..log import get_logger
from .patterns import Pattern

_log = get_logger("rules.snapshot")


def rules_dir() -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return Path(state).expanduser() / "rules"


def path() -> Path:
    return rules_dir() / "patterns.json"


def _source(pattern_file: Path) -> str:
    return str(pattern_file.expanduser().resolve())


def promote(pattern_file: Path, patterns: list[Pattern], now: dt.datetime) -> Path:
    """Replace the snapshot with *patterns*, as promoted from *pattern_file*."""
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".partial")
    partial.write_text(
        json.dumps(
            {
                "source": _source(pattern_file),
                "promoted_at": now.isoformat(timespec="seconds"),
                "patterns": [
                    {**pattern._asdict(), "rule_file": str(pattern.rule_file)}
                    for pattern in patterns
                ],
            },
            indent=2,
        )
    )
    os.replace(partial, target)
    return target


def load(pattern_file: Path) -> list[Pattern]:
    """The patterns last promoted from *pattern_file*; none when another file was promoted, or none was."""
    try:
        data = json.loads(path().read_text())
    except FileNotFoundError:
        _log.info("no promoted patterns; `lemonaid rules check --promote` writes them")
        return []

    if data.get("source") != _source(pattern_file):
        _log.info("the promoted patterns are from %s, not %s", data.get("source"), pattern_file)
        return []

    return [
        Pattern(
            **{
                **entry,
                "rule_file": Path(entry["rule_file"]),
                "match": tuple(entry["match"]),
                "no_match": tuple(entry["no_match"]),
            }
        )
        for entry in data["patterns"]
    ]
