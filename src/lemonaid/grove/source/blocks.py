"""The grove's blocks, trees and lemons from what the inbox read.

A lemon in several groups stands in the first, so it has exactly one place in the grove;
`rooting` says which tree it stands on.
"""

import time
from collections import abc

from ... import brief
from ...inbox import context_use, db, group_lead, model_label, provider_color, turns
from ..model import Block, Lemon, Tree
from . import rooting
from .inputs import Inputs

UNGROUPED_COLOR = "#c9b79c"


def _context(n: db.Notification, thresholds: abc.Mapping[str, context_use.Threshold]) -> str:
    used, window = n.metadata.get("context_tokens"), n.metadata.get("context_window")
    if not isinstance(used, int):
        return ""

    model = n.metadata.get("model")
    threshold = context_use.threshold_for(
        thresholds, n.channel.split(":")[0], model if isinstance(model, str) else ""
    )
    pct = threshold and context_use.percent(
        used, window if isinstance(window, int) else 0, threshold
    )
    return f"{min(pct, 999)}%" if pct is not None and threshold else ""  # as the inbox caps it


def _lemon(
    n: db.Notification,
    inputs: Inputs,
    thresholds: abc.Mapping[str, context_use.Threshold],
    now: float,
    grafted_onto: str,
) -> Lemon:
    card = inputs.cards.get(n.channel)
    status = card.status if card and card.status in brief.store.states() else ""
    if n.asks or (card and card.asking):
        status = "blocked"
    working = card.mid_turn if card else turns.mid_turn(n, now)
    label = model_label.model_label(n.metadata.get("model"))
    lemon_id = inputs.lemon_ids.get(n.channel, "")
    return Lemon(
        channel=n.channel,
        jump_problem=inputs.jump_problems.get(n.channel, ""),
        notification_id=n.id,
        name=n.name or n.channel,
        brief_id=brief.identity.brief_name(lemon_id) if lemon_id else "",
        status=status,
        contested=bool(status and card and card.contested),
        working=working,
        quiet=not status and not working and not n.is_unread,
        model=label[0] if label else "",
        provider=provider_color.provider(n.channel, label[1] if label else ""),
        context=_context(n, thresholds),
        emoji=inputs.emojis.get(n.channel, ""),
        pinned=n.channel in inputs.pinned,
        born=inputs.births.get(n.channel, n.created_at),
        session=str(n.metadata.get("tmux_session") or ""),
        window=str(n.metadata.get("tmux_window") or ""),
        hidden=n.channel in inputs.hidden,
        unread=n.is_unread,
        named="auto_name" in n.metadata,  # kept by `db.update_name` while a given name holds
        branch=str(n.metadata.get("git_branch") or ""),
        cwd=str(n.metadata.get("cwd") or ""),
        age=brief.status.age(max(0.0, now - n.created_at)),
        updated=n.created_at,
        prs=tuple((pr.number, pr.url) for pr in inputs.numbers.get(n.channel, ())),
        grafted_onto=grafted_onto,
    )


def main_first(
    lemons: abc.Iterable[Lemon], lead: str = "", parents: abc.Mapping[str, str] | None = None
) -> tuple[Lemon, ...]:
    """A tree's lemons with its main lemon first, so its lowercase letter always reaches it.

    A lemon grafted on comes after the tree's own, even the group's lead, so the tree's main
    lemon is one that runs in its session. Then the group's lead (channel *lead*) comes first,
    a lemon whose brief is hidden (a reviewer's) comes after one that isn't, a lemon comes after
    its ancestors in the tree (per *parents*, child channel to parent channel), the lower window
    comes first, then the older lemon; the channel settles any tie.
    """
    members = tuple(lemons)
    here = {m.channel for m in members}

    def depth(lemon: Lemon) -> int:
        return len(group_lead.ancestors(lemon.channel, parents or {}) & here)

    def window(lemon: Lemon) -> int:
        return int(lemon.window) if lemon.window.isdigit() else 1_000_000

    return tuple(
        sorted(
            members,
            key=lambda m: (
                bool(m.grafted_onto),
                m.channel != lead,
                m.hidden,
                depth(m),
                window(m),
                m.born,
                m.channel,
            ),
        )
    )


def _trees(
    rows: abc.Sequence[db.Notification],
    lemons: abc.Mapping[str, Lemon],
    roots: abc.Mapping[str, rooting.Rooted],
    lead: str,
    parents: abc.Mapping[str, str],
) -> tuple[Tree, ...]:
    by_key: dict[str, list[Lemon]] = {}
    labels: dict[str, str] = {}
    for n in rows:
        key, labels[key], _ = roots[n.channel]
        by_key.setdefault(key, []).append(lemons[n.channel])
    trees = [
        Tree(
            key,
            labels[key],
            main_first(members, lead, parents),
            any(m.channel == lead for m in members),
        )
        for key, members in by_key.items()
    ]
    return tuple(sorted(trees, key=lambda tree: tree.born))


def _packhouse_lead(
    loose: abc.Sequence[db.Notification],
    rows: abc.Sequence[db.Notification],
    parents: abc.Mapping[str, str],
) -> str:
    """The loose lemon with the most descendants anywhere, since HQ's children are in groups."""
    lineages = [group_lead.ancestors(n.channel, parents) for n in rows]
    counts = [(sum(n.channel in above for above in lineages), n.channel) for n in loose]
    best = max(counts, key=lambda pair: pair[0], default=(0, ""))
    return best[1] if best[0] else ""


def blocks(
    inputs: Inputs,
    thresholds: abc.Mapping[str, context_use.Threshold],
    now: float | None = None,
    home: str = "",
    first: int = 0,
) -> tuple[Block, ...]:
    """Block *first* (0 or 1) for the lemons in no group, and one block per group with live lemons,
    numbered on from it in the inbox's group order. The *home* group's lemons are in block *first*,
    which takes its name and color, and its lead.
    """
    now = time.time() if now is None else now
    roots = rooting.rooted(inputs.rows, inputs.lemon_ids, inputs.grafts)
    lemons = {
        n.channel: _lemon(n, inputs, thresholds, now, roots[n.channel].grafted_onto)
        for n in inputs.rows
    }
    first_group = {channel: names[0] for channel, names in inputs.memberships.items() if names}
    found: list[Block] = []
    for group in (g for g in inputs.groups if g.name != home):
        rows = [n for n in inputs.rows if first_group.get(n.channel) == group.name]
        if rows:
            lead = group_lead.find(rows, inputs.parents)
            found.append(
                Block(
                    group.name,
                    str(first + len(found) + 1),
                    group.color,
                    _trees(rows, lemons, roots, lead, inputs.parents),
                )
            )
    homed = [n for n in inputs.rows if home and first_group.get(n.channel) == home]
    loose = [n for n in inputs.rows if n.channel not in first_group] + homed
    color = next((g.color for g in inputs.groups if homed and g.name == home), UNGROUPED_COLOR)
    if loose:
        lead = (
            group_lead.find(homed, inputs.parents)
            if homed
            else _packhouse_lead(loose, inputs.rows, inputs.parents)
        )
        found.append(
            Block(
                "",
                str(first),
                color,
                _trees(loose, lemons, roots, lead, inputs.parents),
                home if homed else "",
            )
        )
    return tuple(found)
