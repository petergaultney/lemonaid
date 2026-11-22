"""The pattern file: each `[[pattern]]` is a regex, the rule a match may show broken, and what a match does.

`rule_file` and `rule_starts` name the paragraph or list item that states the rule, so
the file never holds a copy of it. A relative `rule_file` is read from the pattern
file's directory.
"""

import collections
import tomllib
import typing as ty
from collections import abc
from pathlib import Path

MODES = ("report", "tell")

_REQUIRED = ("id", "regex", "rule_file", "rule_starts")
_OPTIONAL = ("mode", "say", "cwd")
_EXAMPLES = ("match", "no_match")


class Pattern(ty.NamedTuple):
    id: str
    regex: str
    rule_file: Path
    rule_starts: str
    mode: str  # one of MODES
    say: str  # what to do now, for a lemon told of the match
    cwd: str  # a glob the session's working directory must match; "" for any
    match: tuple[str, ...]
    no_match: tuple[str, ...]


class Parsed(ty.NamedTuple):
    patterns: list[Pattern]  # those that parsed, problems or not elsewhere
    problems: list[str]


def _entry_problems(entry: dict, name: str) -> abc.Iterator[str]:
    for key in sorted(set(entry) - {*_REQUIRED, *_OPTIONAL, *_EXAMPLES}):
        yield f"{name}: unknown key {key!r}"
    for key in _REQUIRED:
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            yield f"{name}: {key} must be a non-empty string"
    for key in _OPTIONAL:
        if not isinstance(entry.get(key, ""), str):
            yield f"{name}: {key} must be a string"
    for key in _EXAMPLES:
        found = entry.get(key, [])
        if not isinstance(found, list) or not all(isinstance(each, str) for each in found):
            yield f"{name}: {key} must be a list of strings"
    if entry.get("mode", "report") not in MODES:
        yield f"{name}: mode must be one of {', '.join(MODES)}"


def _rule_file(raw: str, base: Path) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else base / path


def _pattern(entry: dict, base: Path) -> Pattern:
    return Pattern(
        id=entry["id"].strip(),
        regex=entry["regex"],
        rule_file=_rule_file(entry["rule_file"], base),
        rule_starts=entry["rule_starts"],
        mode=entry.get("mode", "report"),
        say=entry.get("say", "").strip(),
        cwd=entry.get("cwd", "").strip(),
        match=tuple(entry.get("match", ())),
        no_match=tuple(entry.get("no_match", ())),
    )


def parse(text: str, base: Path) -> Parsed:
    """*base* is the directory a relative `rule_file` is read from."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return Parsed([], [f"not valid TOML: {error}"])

    entries = data.get("pattern", [])
    if not isinstance(entries, list) or not entries:
        return Parsed([], ["no [[pattern]] tables"])

    ids = collections.Counter(
        entry["id"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    )
    problems = [
        f"{name}: {count} patterns share this id" for name, count in ids.items() if count > 1
    ]
    patterns = []
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            problems.append(f"pattern {number}: not a table")
            continue

        name = entry["id"] if isinstance(entry.get("id"), str) else f"pattern {number}"
        found = list(_entry_problems(entry, name))
        problems.extend(found)
        if not found:
            patterns.append(_pattern(entry, base))
    return Parsed(patterns, problems)


def load(path: Path) -> Parsed:
    """A relative `rule_file` is resolved against *path*'s directory, never the caller's."""
    path = path.expanduser().absolute()
    try:
        text = path.read_text()
    except OSError as error:
        return Parsed([], [f"cannot read {path}: {error}"])

    return parse(text, path.parent)
