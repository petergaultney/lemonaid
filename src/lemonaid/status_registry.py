"""Brief statuses: the words a brief's Status line may hold, and how lemonaid shows each.

Every status says the next move isn't the lemon's own; a brief with no status is the
lemon's to move. `done` is built in and ends the work. The other words are defaults that
`[[brief.statuses]]` entries in the config change, or add to.
"""

import re
import sys
import typing as ty
from collections import abc


class Status(ty.NamedTuple):
    name: str
    description: str  # when to use it, for `brief statuses` and `brief status --help`
    fill: str  # badge, dot and headline fill
    text: str  # the word on a dark background
    text_light: str  # the word on a light background
    on_fill: str  # text drawn on the fill
    glyph: str  # one character, for group-header badges
    rank: int  # inbox and grove order, most urgent first
    attention: bool  # kept as a row in the inbox's attention mode
    yours: bool  # the user's move: named when the lemon goes done, and before a toss


DONE = "done"

DEFAULTS = (
    Status(
        "alert",
        "the user's move is needed and harm grows while it waits (prod broken, spend"
        " running, data at risk); keep it rare",
        "#c62828",
        "#ff5c5c",
        "#c62828",
        "#ffffff",
        "!",
        10,
        True,
        True,
    ),
    Status(
        "blocked",
        "the user can act now: a decision, an answer, something to review or try",
        "#e3cf65",
        "#e3cf65",
        "#8a6d00",
        "#000000",
        "?",
        20,
        True,
        True,
    ),
    Status(
        "running",
        "nobody's move; you are minding a long pipeline or process, named under"
        " `### Running` in `## Now` (your own test suite is not one)",
        "#00838f",
        "#4fc3cc",
        "#00707a",
        "#ffffff",
        "N",
        30,
        True,
        False,
    ),
    Status(
        "merge",
        "only the user's merge remains: the PR is approved, has no failed CI (green isn't"
        " waited for), no conflicts, and is out of draft; check `gh pr view <n> --json"
        " mergeable`",
        "#4fb35a",
        "#4fb35a",
        "#2e7d32",
        "#000000",
        "m",
        40,
        True,
        True,
    ),
    Status(
        "approve",
        "you reviewed a teammate's PR and recommend the user approve it; a review of a"
        " lemon's PR hands the task back to its author instead",
        "#7e57c2",
        "#b39ddb",
        "#5e35b1",
        "#ffffff",
        "✓",
        50,
        True,
        True,
    ),
    Status(
        "review",
        "the next move is a review or a response from someone outside the grove: a"
        " teammate, a maintainer, an outside party",
        "#8a5a2b",
        "#c08a52",
        "#8a5a2b",
        "#ffffff",
        "r",
        60,
        False,
        False,
    ),
    Status(
        DONE,
        "nothing is left: the PR is merged or closed, or the output accepted, and no waiter"
        " runs; an open PR is never done",
        "#285995",
        "#6f9fe0",
        "#285995",
        "#ffffff",
        "d",
        1000,
        False,
        False,
    ),
)

_FIELDS = frozenset(Status._fields) - {"name"}
_FLAGS = frozenset({"attention", "yours"})
_COLORS = frozenset({"fill", "text", "text_light", "on_fill"})
_NAME = re.compile(r"[a-z][a-z0-9_-]*")
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _entry(raw: object, base: Status | None) -> Status:
    """One `[[brief.statuses]]` table over *base* (a default it changes, or None for a new
    word). Raises ValueError for anything it can't use."""
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"]:
        raise ValueError("each [[brief.statuses]] entry needs a name")

    name = raw["name"].strip().lower()
    if not _NAME.fullmatch(name) or name in ("clear", "working", "waiting"):
        raise ValueError(f"{name!r} can't be a status")

    if unknown := sorted(set(raw) - _FIELDS - {"name", "color"}):
        raise ValueError(f"{name}: unknown field {', '.join(unknown)}")

    fields = dict(raw)
    if color := fields.pop("color", None):
        fields = {"fill": color, "text": color, "text_light": color, **fields}
    for key, value in fields.items():
        expected = bool if key in _FLAGS else int if key == "rank" else str
        if key != "name" and not isinstance(value, expected):
            raise ValueError(f"{name}: {key} must be {expected.__name__}")

        if key in _COLORS and not _HEX.fullmatch(value):
            raise ValueError(f"{name}: {key} must be a color like #8d6e63")

    if base is None:
        if "fill" not in fields:
            raise ValueError(f"{name}: a new status needs a color")

        base = Status(name, "", "", "", "", "#ffffff", name[0], 500, False, False)
    return base._replace(**{k: v for k, v in fields.items() if k != "name"}, name=name)


def parse(raw: object) -> tuple[Status, ...]:
    """The configured statuses, most urgent first: the defaults, changed or added to by
    *raw*, the `[[brief.statuses]]` list. An entry it can't use is skipped with a warning,
    and `done` can't be changed."""
    found = {s.name: s for s in DEFAULTS}
    for entry in raw if isinstance(raw, list) else []:
        try:
            name = str(entry.get("name", "")).strip().lower() if isinstance(entry, dict) else ""
            if name == DONE:
                raise ValueError("done is built in and can't be changed")

            status = _entry(entry, found.get(name))
        except ValueError as error:
            print(f"Warning: [[brief.statuses]] {error}", file=sys.stderr)
            continue

        found[status.name] = status
    return tuple(sorted(found.values(), key=lambda s: (s.rank, s.name)))


def names(statuses: abc.Iterable[Status]) -> tuple[str, ...]:
    return tuple(s.name for s in statuses)


def by_name(statuses: abc.Iterable[Status]) -> dict[str, Status]:
    return {s.name: s for s in statuses}


def attention(statuses: abc.Iterable[Status]) -> frozenset[str]:
    """The statuses that keep a row in the inbox's attention mode."""
    return frozenset(s.name for s in statuses if s.attention)


def yours(statuses: abc.Iterable[Status]) -> frozenset[str]:
    """The statuses that mean the user moves next."""
    return frozenset(s.name for s in statuses if s.yours)
