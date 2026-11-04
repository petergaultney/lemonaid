"""Sending the inspector's challenges to the briefs they name, once per set of facts.

A case is checked again just before it is sent, so a task closed, reassigned or given a
disposition since its evaluation sends nothing. Each case's message is named by a key
hashed from its facts (subject, obligation, evidence, recipient and basis), so its read
receipt is found again without storing the message ID, and a case reopened on the same facts
finds the message already sent. A message its lemon received is never sent again; one still
waiting (the lemon was dead or deaf) is replaced by a fresh copy every interval.
"""

import functools
import hashlib
import sqlite3
import typing as ty
from collections import abc

from ...messages import receipts, store
from ..briefs import registration
from ..model import identities, ledger
from . import cases


def _covered(conn: sqlite3.Connection, case: ty.Mapping[str, ty.Any]) -> bool:
    """Whether a missing-task case's brief has a disposition now."""
    subject = case["subject"]
    return subject.startswith("brief:") and bool(
        registration.disposition(conn, subject.removeprefix("brief:"))
    )


def _body(case: ty.Mapping[str, ty.Any]) -> str:
    return (
        f"The task inspector, about {case['subject']} ({case['obligation']}):\n\n{case['reason']}"
    )


def message_key(case: ty.Mapping[str, ty.Any]) -> str:
    facts = "\n".join(
        str(case[k])
        for k in ("subject", "obligation", "evidence", "target_kind", "target", "basis")
    )
    return hashlib.sha256(facts.encode()).hexdigest()[:32]


def _due(case: ty.Mapping[str, ty.Any], receipt: str, interval: float, now: float) -> bool:
    """Never sent, or sent and still unreceived for *interval*."""
    if receipt.startswith("delivered"):
        return False

    last = case["notified_at"]
    return last is None or now >= last + interval


def deliver(
    conn: sqlite3.Connection,
    interval: float,
    opted_out: abc.Collection[str],
    now: float,
) -> list[str]:
    """Message each open challenge to a brief that is due, unless the brief is in
    *opted_out*; returns a line per message. With no *interval*, the lines say what would
    be sent. Adjudications and other targets are reported, not sent."""
    lines = []
    for case in cases.open_cases(conn):
        with ledger.transaction(conn):
            cases.superseded(conn, now)  # the task may have moved on since its evaluation
            if _covered(conn, case):
                cases.resolve(conn, case["case_id"], now)
            still = cases.is_open(conn, case["case_id"])
        target = case["target"]
        if (
            not still
            or case["kind"] != "challenge"
            or case["target_kind"] != "brief"
            or any(name in opted_out for name in identities.names(conn, target))
        ):
            continue

        key = message_key(case)
        if not _due(case, receipts.by_key(key), interval, now):
            continue

        if not interval:
            lines.append(f"would tell {target} about {case['subject']} ({case['obligation']})")
            continue

        try:
            mailbox = store.mailbox_for_id(target)
            sent = receipts.resend(
                mailbox,
                key,
                functools.partial(store.send, mailbox, _body(case), "lemonaid task inspector", key),
            )
        except (ValueError, OSError) as error:
            lines.append(f"telling {target} about {case['subject']} failed: {error}")
            continue

        if not sent:
            continue  # its lemon received it since the receipt was read

        with ledger.transaction(conn):
            cases.notified(conn, case["case_id"], now)
        lines.append(f"told {target} about {case['subject']} ({case['obligation']})")
    return lines
