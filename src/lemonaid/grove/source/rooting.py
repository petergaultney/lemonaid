"""Which tree each lemon is rooted in: its terminal workspace's (a tmux session or a WezTerm
workspace), else its directory's; or, grafted onto another lemon, that lemon's, for as long as it
is live. A graft onto a lemon that isn't live waits, and its lemon stands on its own tree until
the host comes back.
"""

import typing as ty
from collections import abc

from ... import front_end
from ...inbox import db


class Rooted(ty.NamedTuple):
    key: str
    label: str
    grafted_onto: str  # its host as the graft names it, or "" on its own tree


def _workspace(n: db.Notification) -> tuple[str, str]:
    """(key, label) of *n*'s own tree. A tmux tree's key is its session, which renaming the tree
    renames; another front end's key holds its instance too, so equal names never merge.
    """
    where = front_end.location.of(n.metadata, n.switch_source)
    if where.front_end == "tmux" and where.workspace:
        return where.workspace, where.workspace

    if where.workspace:
        return f"{where.front_end}:{where.instance}:{where.workspace}", where.workspace

    place = str(n.metadata.get("cwd") or n.channel)
    return place, place


def _onto(channel: str, lemon_ids: abc.Mapping[str, str], grafts: abc.Mapping[str, str]) -> str:
    return grafts.get(lemon_ids.get(channel, ""), "") or grafts.get(channel, "")


def _hosts(
    channels: abc.Collection[str], lemon_ids: abc.Mapping[str, str], grafts: abc.Mapping[str, str]
) -> dict[str, str]:
    """The channel of the live lemon whose tree each moved lemon stands on, by channel; a lemon
    in a loop of grafts stays on its own tree."""
    by_name = {name: c for c in channels for name in (c, lemon_ids.get(c, "")) if name}

    def step(channel: str) -> str:
        return by_name.get(_onto(channel, lemon_ids, grafts), "")

    found: dict[str, str] = {}
    for channel in channels:
        at, seen = step(channel), {channel}
        while at and at not in seen:
            seen.add(at)
            if not step(at):
                found[channel] = at
                break

            at = step(at)
    return found


def rooted(
    rows: abc.Iterable[db.Notification],
    lemon_ids: abc.Mapping[str, str],
    grafts: abc.Mapping[str, str],
) -> dict[str, Rooted]:
    """Each live lemon's tree, by channel. *grafts* (as `grafts.recorded` gives them) name lemons
    and hosts by Lemon-ID, per *lemon_ids*, or by channel."""
    by_channel = {n.channel: n for n in rows}
    hosts = _hosts(by_channel.keys(), lemon_ids, grafts)
    return {
        channel: Rooted(
            *_workspace(by_channel[hosts[channel]] if channel in hosts else n),
            _onto(channel, lemon_ids, grafts) if channel in hosts else "",
        )
        for channel, n in by_channel.items()
    }
