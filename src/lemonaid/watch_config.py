"""Configurable review-thread filters for PR watchers."""

import sys
from collections import abc
from dataclasses import dataclass, field


@dataclass
class PrConfig:
    skip_outdated: bool = False
    skip_resolved: bool = False
    trusted_commenters: frozenset[str] = frozenset()  # "host/login", see _qualified


@dataclass
class WatchConfig:
    pr: PrConfig = field(default_factory=PrConfig)


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
        )
    )
