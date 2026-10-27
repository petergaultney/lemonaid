"""Attention mode's line at the top of the inbox: how many lemons have each status.

Each count is drawn as its group header badge, `!2` or `?1`. Where the group bars give each
status a slot, the badge sits in that slot's column; otherwise the statuses that keep a row
come first, then a divider, then the ones that fold.
"""

from collections import Counter, abc

from rich.text import Text

from ... import db
from . import group_headers

# Where each status's count sits; any other status follows these, by name.
_ORDER = (
    "alert",
    "blocked",
    "running",
    "merge",
    "approve",
    "review",
    "done",
    "active",
    "idle",
    "deaf",
    "dead",
    "",
)


def _counts(rows: abc.Iterable[db.Notification], statuses: abc.Mapping[str, str]) -> Counter[str]:
    return Counter(statuses.get(channel, "") for channel in {n.channel for n in rows})


def _ordered(statuses: abc.Iterable[str]) -> list[str]:
    return sorted(
        statuses, key=lambda s: (_ORDER.index(s), "") if s in _ORDER else (len(_ORDER), s)
    )


def _part(statuses: abc.Sequence[str], every: Counter[str]) -> Text:
    """A group header's badge for each status, then one dim count for those without a badge."""
    plain = sum(every[s] for s in statuses if not group_headers.has_badge(s))
    return Text.assemble(
        *(group_headers.badge(s, every[s]) for s in statuses if group_headers.has_badge(s)),
        Text(f" ○{plain}", "dim") if plain else "",
    )


def slot_width(rows: abc.Iterable[db.Notification], statuses: abc.Mapping[str, str]) -> int:
    """The widest badge this line draws, so the group bars' slots can hold it too."""
    return max(
        (
            group_headers.badge(s, n).cell_len
            for s, n in _counts(rows, statuses).items()
            if group_headers.has_badge(s)
        ),
        default=0,
    )


def _in_slots(left: Text, every: Counter[str], starts: abc.Mapping[str, int], slot: int) -> Text:
    """*left*, then each status's badge right-justified in its slot at *starts*."""
    text = left.copy()
    for status, start in sorted(starts.items(), key=lambda item: item[1]):
        if not every[status]:
            continue

        mark = group_headers.badge(status, every[status])
        text.truncate(start, overflow="ellipsis")
        text.pad_right(start + slot - mark.cell_len - text.cell_len)
        text.append_text(mark)
    return text


def line(
    rows: abc.Iterable[db.Notification],
    statuses: abc.Mapping[str, str],
    attention_statuses: abc.Collection[str],
    sidebar: bool,
    fold_key: str,
    fold_open: bool,
    starts: abc.Mapping[str, int],
    slot: int,
) -> Text:
    """*rows* counted by their *statuses*. Badges go in the columns at *starts*, each *slot*
    wide, when given; else those in *attention_statuses* come before the divider.
    """
    every = _counts(rows, statuses)
    present = _ordered(every)
    kept = [s for s in present if s in attention_statuses]
    folded = [s for s in present if s not in attention_statuses]
    nothing = Text("none" if sidebar else "nothing needs you", "dim")
    hint = (
        (fold_key if sidebar else f"{fold_key} {'folds' if fold_open else 'shows all'}")
        if fold_key
        else ""
    )
    gap = "  " if sidebar else "   "
    if starts:
        plain = sum(every[s] for s in present if not group_headers.has_badge(s))
        text = _in_slots(
            Text.assemble(
                " ",
                "" if kept else nothing,
                Text(f"{' ' if not kept else ''}○{plain}", "dim") if plain else "",
                Text(gap + hint, "dim") if hint else "",
            ),
            every,
            starts,
            slot,
        )
    else:
        text = Text.assemble(
            " ",
            _part(kept, every) if kept else nothing,
            Text(" │", "dim"),
            _part(folded, every),
            Text(gap + hint, "dim") if hint else "",
        )
    text.no_wrap = True
    text.overflow = "ellipsis"
    return text
