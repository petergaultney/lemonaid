"""What a doc's frontmatter declares: the packages it belongs to, the lemons a package
is for (`package-for`, on the package's index doc), its triggers (`load-when`) and its
`reminder` line."""

import re
from collections import abc
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..log import get_logger

_log = get_logger("docs.frontmatter")

KINDS = ("command", "edit", "create", "prompt")
_KEYS = ("package", "package-for", "load-when")
_TRIGGER_KEYS = (*KINDS, "section", "before")


@dataclass(frozen=True)
class Trigger:
    kind: str  # one of KINDS
    pattern: str  # a regex for command and prompt, a glob for edit and create
    section: str = ""  # the heading whose section it delivers; the whole doc when ""
    before: bool = False  # refuse the first matching call, with the section as the reason
    lemon: dict = field(default_factory=dict)  # `package-for` keys the lemon must also match


@dataclass(frozen=True)
class Doc:
    path: Path
    packages: tuple[str, ...] = ()  # the packages it belongs to
    triggers: tuple[Trigger, ...] = ()
    reminder: str = ""
    lemons: tuple[dict, ...] = ()  # `package-for`, on a package's index doc


def package_name(doc: Doc) -> str:
    """The package *doc* is the index of, or "" when it is none."""
    return doc.path.stem if doc.lemons else ""


def fields(path: Path) -> dict:
    """The mapping in *path*'s frontmatter, read without the rest of the file; {} without one."""
    try:
        with path.open(encoding="utf-8") as f:
            if f.readline().rstrip() != "---":
                return {}

            block = []
            for line in f:
                if line.rstrip() in ("---", "..."):
                    break
                block.append(line)
            else:
                return {}
        loaded = yaml.safe_load("".join(block))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        _log.warning("skipped %s: %s", path, str(e).splitlines()[0])
        return {}

    return loaded if isinstance(loaded, dict) else {}


def _names(path: Path, raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and all(isinstance(r, str) for r in raw):
        return tuple(raw)
    if raw is not None:
        _log.warning("%s: package must be a name or a list of names, not %r", path, raw)
    return ()


def _trigger(path: Path, raw: object) -> Trigger | None:
    kinds = [k for k in KINDS if k in raw] if isinstance(raw, dict) else []
    if not isinstance(raw, dict) or len(kinds) != 1 or not isinstance(raw[kinds[0]], str):
        _log.warning(
            "%s: a load-when item needs one of %s, as text: %r", path, ", ".join(KINDS), raw
        )
        return None

    kind = kinds[0]
    if kind in ("command", "prompt"):
        try:
            re.compile(raw[kind])
        except re.error as e:
            _log.warning("%s: load-when %s %r: %s", path, kind, raw[kind], e)
            return None

    return Trigger(
        kind,
        raw[kind],
        str(raw.get("section") or ""),
        raw.get("before") is True,
        {key: value for key, value in raw.items() if key not in _TRIGGER_KEYS},
    )


def _list(path: Path, key: str, raw: object) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw

    _log.warning("%s: %s must be a list, not %r", path, key, raw)
    return []


def _lemons(path: Path, raw: object) -> abc.Iterator[dict]:
    for item in _list(path, "package-for", raw):
        if isinstance(item, dict):
            yield item
        else:
            _log.warning("%s: a package-for item must be a mapping, not %r", path, item)
            yield {"not": {}}  # keeps the doc a package's index, for nobody


def parse(path: Path, declared: abc.Mapping) -> Doc | None:
    """*path*'s doc from its frontmatter *declared*, or None when it declares nothing."""
    if not any(key in declared for key in _KEYS):
        return None

    reminder = declared.get("reminder")
    return Doc(
        path=path,
        packages=_names(path, declared.get("package")),
        triggers=tuple(
            t
            for raw in _list(path, "load-when", declared.get("load-when"))
            if (t := _trigger(path, raw))
        ),
        reminder=reminder.strip() if isinstance(reminder, str) else "",
        lemons=tuple(_lemons(path, declared.get("package-for"))),
    )
