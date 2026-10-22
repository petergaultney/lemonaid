"""Ranking a group's members by lineage: the lead, and who must be drawn with whom."""

from collections import abc

from . import db


def ancestors(channel: str, parents: abc.Mapping[str, str]) -> set[str]:
    found: set[str] = set()
    while (parent := parents.get(channel, "")) and parent not in found and parent != channel:
        found.add(parent)
        channel = parent

    return found


def find(rows: abc.Sequence[db.Notification], parents: abc.Mapping[str, str]) -> str:
    """The channel of the member with the most descendants among *rows*, or "".

    *rows* are the group's members that have inbox sessions, in group order, which
    breaks ties. A member with no descendants in the group leads nothing, so a group
    without lineage has no lead. Lineage may pass through lemons outside the group.
    """
    lineages = [(n.channel, ancestors(n.channel, parents)) for n in rows]
    counts = [(sum(c in above for _, above in lineages), c) for c, _ in lineages]
    best = max(counts, key=lambda pair: pair[0], default=(0, ""))

    return best[1] if best[0] else ""
