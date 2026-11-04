"""The grove's blocks, trees and lemons from what the inbox read.

A lemon in several groups stands in the first, so it has exactly one place in the grove.
Lemons share a tree when they run in the same terminal workspace (a tmux session or a
WezTerm workspace), or otherwise in the same directory.
"""

import time
from collections import abc

from ... import brief, front_end
from ...inbox import context_use, db, group_lead, model_label, provider_color, turns
from ..model import Block, Lemon, Tree
from .inputs import Inputs

UNGROUPED_COLOR = "#c9b79c"


def _tree(n: db.Notification) -> tuple[str, str]:
    """(key, label) of *n*'s tree. A tmux tree's key is its session, which renaming the tree
    renames; another front end's key holds its instance too, so equal names never merge.
    """
    where = front_end.location.of(n.metadata, n.switch_source)
    if where.front_end == "tmux" and where.workspace:
        return where.workspace, where.workspace

    if where.workspace:
        return f"{where.front_end}:{where.instance}:{where.workspace}", where.workspace

    place = str(n.metadata.get("cwd") or n.channel)
    return place, place


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
    )


def main_first(
    lemons: abc.Iterable[Lemon], lead: str = "", parents: abc.Mapping[str, str] | None = None
) -> tuple[Lemon, ...]:
    """A tree's lemons with its main lemon first, so its lowercase letter always reaches it.

    The group's lead (channel *lead*) comes first; then a lemon whose brief is hidden (a
    reviewer's) comes after one that isn't, then a lemon comes after its ancestors in the tree
    (per *parents*, child channel to parent channel), then the lower window comes first, then
    the older lemon; the channel settles any tie.
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
            key=lambda m: (m.channel != lead, m.hidden, depth(m), window(m), m.born, m.channel),
        )
    )


def _trees(
    rows: abc.Sequence[db.Notification],
    lemons: abc.Mapping[str, Lemon],
    lead: str,
    parents: abc.Mapping[str, str],
) -> tuple[Tree, ...]:
    by_key: dict[str, list[Lemon]] = {}
    labels: dict[str, str] = {}
    for n in rows:
        key, labels[key] = _tree(n)
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
    inputs: Inputs, thresholds: abc.Mapping[str, context_use.Threshold], now: float | None = None
) -> tuple[Block, ...]:
    """One block per group with live lemons, numbered in the inbox's group order, and block 0 for the rest."""
    now = time.time() if now is None else now
    lemons = {n.channel: _lemon(n, inputs, thresholds, now) for n in inputs.rows}
    first_group = {channel: names[0] for channel, names in inputs.memberships.items() if names}
    found: list[Block] = []
    for group in inputs.groups:
        rows = [n for n in inputs.rows if first_group.get(n.channel) == group.name]
        if rows:
            lead = group_lead.find(rows, inputs.parents)
            found.append(
                Block(
                    group.name,
                    str(len(found) + 1),
                    group.color,
                    _trees(rows, lemons, lead, inputs.parents),
                )
            )
    loose = [n for n in inputs.rows if n.channel not in first_group]
    if loose:
        found.append(
            Block(
                "",
                "0",
                UNGROUPED_COLOR,
                _trees(
                    loose,
                    lemons,
                    _packhouse_lead(loose, inputs.rows, inputs.parents),
                    inputs.parents,
                ),
            )
        )
    return tuple(found)
