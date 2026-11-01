"""The default checker's settings and fact lookups.

Settings come from `policy.*` context fields, defaulting to the handoff's trial values.
"""

import datetime
import typing as ty

from .. import checker_input

_DEFAULTS = {
    "policy.idle_grace": 120,
    "policy.unstarted_grace": 600,
    "policy.reconcile": 300,
    "policy.coverage_grace": 600,
}


class Unknown(Exception):
    pass


class Policy(ty.NamedTuple):
    now: datetime.datetime
    idle_grace: datetime.timedelta
    unstarted_grace: datetime.timedelta
    reconcile: datetime.timedelta
    coverage_grace: datetime.timedelta


def read(context: ty.Mapping[str, str]) -> Policy:
    def seconds(name: str) -> datetime.timedelta:
        return datetime.timedelta(seconds=int(context.get(name, _DEFAULTS[name])))

    return Policy(
        checker_input.timestamp(context["now"]),
        seconds("policy.idle_grace"),
        seconds("policy.unstarted_grace"),
        seconds("policy.reconcile"),
        seconds("policy.coverage_grace"),
    )


def fact(view: checker_input.View, kind: str, key: str, field: str) -> str:
    found = view.facts.get((kind, key, field))
    if found is None or found.availability != "known":
        raise Unknown(f"{kind} {key} {field} is {found.availability if found else 'missing'}")

    return found.value


def at(policy: Policy, moment: datetime.datetime) -> str:
    return checker_input.rfc3339(max(moment, policy.now))
