"""The lost lemons grouped by the front end (terminal) that restores them."""

import typing as ty
from collections import abc

from ..config import Config
from ..front_end import interface, pick, terminals
from ..inbox import db
from . import report, run


def _by_front_end(rows: abc.Iterable[db.Notification]) -> dict[str, list[db.Notification]]:
    grouped: dict[str, list[db.Notification]] = {}
    for row in rows:
        grouped.setdefault(row.switch_source or "", []).append(row)
    return grouped


def _unable(front_end: str, rows: abc.Iterable[db.Notification]) -> list[report.Result]:
    why = f"lemonaid can't restore lemons in {front_end or 'an unrecorded terminal'}"
    return [
        report.Result(row.channel, row.name or row.channel, "", report.NOT_RESTORED, why)
        for row in rows
    ]


def _cannot_type(row: db.Notification, config: Config, text: str) -> str:
    return "its terminal can't type into a lemon"


class Group(ty.NamedTuple):
    terminal: run.Terminal
    prompt: interface.Revive
    rows: list[db.Notification]


def groups(
    lost: abc.Iterable[db.Notification], start: bool
) -> tuple[list[Group], list[report.Result]]:
    """The lost lemons grouped by the front end that restores them, and a result for each
    whose front end can't. Without *start*, no front end starts its terminal to do it."""
    found: list[Group] = []
    unable: list[report.Result] = []
    for name, rows in _by_front_end(lost).items():
        front_end = pick.named(name)
        if front_end is None or front_end.restore is None:
            unable += _unable(name, rows)
        else:
            found.append(Group(front_end.restore(start), front_end.prompt or _cannot_type, rows))
    return found, unable


def restorers() -> list[run.Terminal]:
    """Every front end that restores lemons, whether or not any was lost in it, none of
    them starting its terminal."""
    return [
        front_end.restore(False)
        for each in terminals.all_terminals()
        if (front_end := pick.named(each.name)) and front_end.restore
    ]
