"""Configurable review-thread filters, role wake lists and GitHub outage debounce for watchers."""

import sys
from collections import abc
from dataclasses import dataclass, field

from .watch import roles


@dataclass
class PrConfig:
    skip_outdated: bool = False
    skip_resolved: bool = False
    trusted_commenters: frozenset[str] = frozenset()  # "host/login", see _qualified


@dataclass
class WatchConfig:
    pr: PrConfig = field(default_factory=PrConfig)
    roles: dict[str, frozenset[str]] = field(default_factory=dict)  # see watch/roles.py
    github_debounce: float = 600.0  # seconds GitHub must stay unreachable before a lemon hears
    reconcile: bool = True  # see watch/reconcile.py


_CASELESS_HOSTS = frozenset({"github.com"})  # hosts whose logins are unique regardless of case


def _qualified(entry: str) -> str:
    """`host/login`, or "" for an entry not written that way; a caseless host's login is lowercased."""
    host, _, login = entry.rpartition("/")
    if not host or not login or ":" in host or "/" in host:
        return ""

    host = host.lower()
    return f"{host}/{login.lower() if host in _CASELESS_HOSTS else login}"


def logins_on(trusted: abc.Iterable[str], host: str) -> frozenset[str]:
    """The trusted logins on *host*, as that host's comments name them."""
    entries = (entry.rpartition("/") for entry in trusted)
    return frozenset(login for on, _, login in entries if on == host)


def _roles(data: object) -> dict[str, frozenset[str]]:
    if not isinstance(data, dict):
        print("Warning: [watch.roles] must be a table of roles", file=sys.stderr)
        return {}

    found = {}
    for role, table in data.items():
        wake = table.get("wake") if isinstance(table, dict) else None
        if role not in roles.ROLES:
            print(
                f"Warning: [watch.roles.{role}] is ignored; roles are {', '.join(roles.ROLES)}",
                file=sys.stderr,
            )
        elif not isinstance(wake, list) or not all(k in roles.KINDS for k in wake):
            print(
                f"Warning: [watch.roles.{role}] wake must be a list of {', '.join(roles.KINDS)};"
                " keeping the default",
                file=sys.stderr,
            )
        else:
            found[role] = frozenset(wake)
    return found


def _debounce(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        print("Warning: [watch] github_debounce must be seconds, 0 or more", file=sys.stderr)
        return WatchConfig.github_debounce

    return float(value)


def _reconcile(value: object) -> bool:
    if not isinstance(value, bool):
        print("Warning: [watch] reconcile must be true or false", file=sys.stderr)
        return WatchConfig.reconcile

    return value


def parse(data: dict) -> WatchConfig:
    pr = data.get("pr", {})
    values: dict[str, bool] = {}
    for key in ("skip_outdated", "skip_resolved"):
        value = pr.get(key, False)
        if not isinstance(value, bool):
            print(f"Warning: [watch.pr] {key} must be a boolean", file=sys.stderr)
            value = False
        values[key] = value
    trusted = pr.get("trusted_commenters", [])
    if not isinstance(trusted, list) or not all(isinstance(t, str) for t in trusted):
        print("Warning: [watch.pr] trusted_commenters must be a list of logins", file=sys.stderr)
        trusted = []
    for entry in (t for t in trusted if not _qualified(t)):
        print(
            f"Warning: [watch.pr] trusted_commenters entry {entry!r} is ignored; "
            "write it as host/login, such as github.com/alice",
            file=sys.stderr,
        )
    return WatchConfig(
        pr=PrConfig(
            **values,
            trusted_commenters=frozenset(q for t in trusted if (q := _qualified(t))),
        ),
        roles=_roles(data.get("roles", {})),
        github_debounce=_debounce(data.get("github_debounce", WatchConfig.github_debounce)),
        reconcile=_reconcile(data.get("reconcile", WatchConfig.reconcile)),
    )
