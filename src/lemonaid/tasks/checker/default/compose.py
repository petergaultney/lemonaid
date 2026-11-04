"""How the default checker's rules combine, so a checker of your own can reuse them.

A rule set (`Rules`) groups rules into stages. Within a stage, rules run in order and the
first to return findings decides the stage; a rule returns [] to pass. A rule may raise
`settings.Unknown` (or ValueError, KeyError) when a fact it needs isn't known, and the
subject's finding is then `unknown`.

For an open task, the stages combine as follows:

1. `absent`: its holder can't move (gone, or never started). Runs even while the holder
   is mid-work, and decides the task on its own.
2. A holder working right now is rechecked later.
3. `claims`: a Status its facts contradict. Its challenge is held until the idle grace
   passes, but it stops any `waits` from excusing the holder meanwhile.
4. `waits`: what the holder legitimately waits on (a dependency, running CI).
5. A holder idle for less than the grace is rechecked when it ends.
6. `declared`: a wait the holder's Status declares.
7. `idle`: what to say to a holder with nothing to wait on.
8. `asks`: unlike the stages above, every rule here runs, and its findings are added to
   what steps 2 to 7 decided, such as a request to re-check a Status.

A closed task is decided by `closed`, and a working brief with no task by `uncovered`;
those rules get the whole view. `watches` together declare what the checker watches for a
subject; each returns (kind, key) pairs and lemonaid gathers them all.

To add a rule, put it in the stage it belongs to: `rules.DEFAULT._replace(claims=(mine,
*rules.DEFAULT.claims))` judges your Status rule before the default ones, and before a
declared wait could excuse the holder.
"""

import typing as ty
from collections import abc

from .. import checker_input, protocol
from . import settings

Rule = abc.Callable[[checker_input.View, settings.Policy, str], list[protocol.Record]]

Judge = abc.Callable[[checker_input.View], list[protocol.Record]]

Watches = abc.Callable[[checker_input.View], list[tuple[str, str]]]

_REQUIRED = ("lifecycle", "holder", "revision", "assignment.assigned_at")


class Rules(ty.NamedTuple):
    absent: tuple[Rule, ...]
    claims: tuple[Rule, ...]
    waits: tuple[Rule, ...]
    declared: tuple[Rule, ...]
    idle: tuple[Rule, ...]
    closed: tuple[Judge, ...]
    uncovered: tuple[Judge, ...]
    watches: tuple[Watches, ...]
    asks: tuple[Rule, ...] = ()


def first(
    stage: abc.Iterable[Rule], view: checker_input.View, policy: settings.Policy, holder: str
) -> list[protocol.Record]:
    return next((found for rule in stage if (found := rule(view, policy, holder))), [])


def _judged(stage: abc.Iterable[Judge], view: checker_input.View) -> list[protocol.Record]:
    return next((found for judge in stage if (found := judge(view))), [])


def _progress(
    rules: Rules, view: checker_input.View, policy: settings.Policy, brief: str
) -> list[protocol.Record]:
    if settings.fact(view, "lemon", brief, "activity") == "active":
        return [("recheck", view.subject, settings.at(policy, policy.now + policy.idle_grace))]

    claimed = first(rules.claims, view, policy, brief)
    if not claimed and (found := first(rules.waits, view, policy, brief)):
        return found

    idle_since = max(
        checker_input.timestamp(settings.fact(view, "lemon", brief, "idle_since")),
        checker_input.timestamp(view.fields["assignment.attached_at"]),
    )  # the clock starts no earlier than the assignment, or the lemon's start with it
    if idle_since + policy.idle_grace > policy.now:
        return [("recheck", view.subject, settings.at(policy, idle_since + policy.idle_grace))]

    if claimed:
        return claimed  # no wait makes a contradicted Status true

    return first(rules.declared, view, policy, brief) or first(rules.idle, view, policy, brief)


def _asked(decided: list[protocol.Record], asked: list[protocol.Record]) -> list[protocol.Record]:
    """*decided* with *asked* added; an `ok` gives way to an accusation among them."""
    accused = any(r[0] in ("challenge", "adjudicate") for r in asked)
    return [*(r for r in decided if not (accused and r[0] == "ok")), *asked]


def task(rules: Rules, view: checker_input.View) -> list[protocol.Record]:
    """The complete finding set for the input's task."""
    try:
        if missing := [f for f in _REQUIRED if not view.fields.get(f)]:
            raise settings.Unknown(f"missing task field {', '.join(missing)}")

        policy = settings.read(view.context)
        if view.fields["lifecycle"] == "closed":
            return _judged(rules.closed, view) or [("ok", view.subject, "closed")]

        holder = view.fields["holder"]
        if not holder.startswith("brief:"):
            raise settings.Unknown(f"{holder} isn't a lemon")

        brief = holder.removeprefix("brief:")
        found = first(rules.absent, view, policy, brief) or _asked(
            _progress(rules, view, policy, brief),
            [r for ask in rules.asks for r in ask(view, policy, brief)],
        )
    except (settings.Unknown, ValueError, KeyError) as e:
        return [("unknown", view.subject, str(e))]

    if any(r[0] in ("ok", "challenge", "adjudicate", "wait") for r in found):
        return found

    return [("ok", view.subject, "progressing"), *found]


def brief(rules: Rules, view: checker_input.View) -> list[protocol.Record]:
    """The complete finding set for a working brief with no task."""
    return _judged(rules.uncovered, view) or [("ok", view.subject, "covered")]


def watches(rules: Rules, view: checker_input.View) -> list[tuple[str, str]]:
    return list(dict.fromkeys(w for declare in rules.watches for w in declare(view)))
