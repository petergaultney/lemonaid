"""An arranger's answer, and what the inbox draws from it.

An answer is a JSON object:

    {"rows": [12, 7, 30], "folded": [4, 9], "fold_label": "quiet"}

`rows` is the main list in order, `folded` the group folded at its bottom, and
`fold_label` names that group. Every field is optional. `{"error": "..."}`
says the arranger failed, and the inbox draws its own order meanwhile.

The answer decides display only, and nothing it does loses a row: a row it
leaves out goes where the inbox's own order puts it, and an unread row stays
out of the fold unless the user allows otherwise.
"""

import dataclasses
from collections import abc
from typing import Any

from .. import db

_FIELDS = frozenset({"version", "rows", "folded", "fold_label", "error"})


class AnswerError(ValueError):
    """The answer can't be used at all, so the inbox draws its own order."""


@dataclasses.dataclass(frozen=True)
class Arranged:
    shown: list[db.Notification]
    folded: list[db.Notification]
    fold_label: str
    problems: list[str]  # what was ignored or corrected, for logs and `arrange check`


def default(snapshot: abc.Mapping[str, Any]) -> dict[str, Any]:
    """The inbox's own answer to *snapshot*, to start from and change."""
    rows = sorted(snapshot["rows"], key=lambda r: r["default"]["position"])
    return {
        "rows": [r["id"] for r in rows if not r["default"]["folded"]],
        "folded": [r["id"] for r in rows if r["default"]["folded"]],
    }


def _ids(answer: abc.Mapping[str, Any], field: str) -> list[int]:
    ids = answer.get(field, [])
    if not isinstance(ids, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in ids
    ):
        raise AnswerError(f"{field!r} must be a list of row ids")

    return ids


def apply(
    answer: object,
    shown: abc.Sequence[db.Notification],
    folded: abc.Sequence[db.Notification],
    may_fold_unread: bool,
) -> Arranged:
    """*answer* applied to the inbox's own *shown* and *folded* rows."""
    if not isinstance(answer, dict):
        raise AnswerError(f"answer must be a JSON object, not {type(answer).__name__}")

    if "error" in answer:
        raise AnswerError(f"arranger says: {answer['error']}")

    label = answer.get("fold_label", "")
    if not isinstance(label, str):
        raise AnswerError("'fold_label' must be a string")

    by_id = {n.id: n for n in [*shown, *folded]}
    problems = [f"unknown field {key!r} ignored" for key in sorted(answer.keys() - _FIELDS)]
    placed: set[int] = set()
    out_shown: list[db.Notification] = []
    out_folded: list[db.Notification] = []
    kept_out: list[db.Notification] = []
    for field, out in (("rows", out_shown), ("folded", out_folded)):
        for i in _ids(answer, field):
            if i not in by_id:
                problems.append(f"{field}: no row {i}, ignored")
            elif i in placed:
                problems.append(f"{field}: row {i} placed twice, first kept")
            elif out is out_folded and by_id[i].is_unread and not may_fold_unread:
                problems.append(f"folded: row {i} is unread, kept in the list")
                kept_out.append(by_id[i])
                placed.add(i)
            else:
                out.append(by_id[i])
                placed.add(i)

    for rows, out in ((shown, out_shown), (folded, out_folded)):
        missing = [n for n in rows if n.id not in placed]
        if missing:
            problems.append(
                f"rows {', '.join(str(n.id) for n in missing)} left out,"
                " added where the inbox's own order puts them"
            )
        out.extend(missing)

    return Arranged([*out_shown, *kept_out], out_folded, label, problems)
