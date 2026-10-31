"""Builders for synthetic task snapshots; no real corpus data belongs in this repo."""

import typing as ty

NOW = "2026-10-31T12:00:00Z"


def task(**fields: str) -> dict[str, str]:
    return {
        "task_id": "t1",
        "lifecycle": "open",
        "holder": "brief:Work.alpha",
        "revision": "3",
        "sponsor": "Lead.lead",
        "assignment.transfer_event": "e3",
        "assignment.assigned_at": "2026-10-31T11:00:00Z",
        "assignment.attached_at": "2026-10-31T11:01:00Z",
        "assignment.acknowledged_at": "2026-10-31T11:02:00Z",
        **fields,
    }


def fact(
    kind: str, key: str, field: str, value: str, availability: str = "known"
) -> dict[str, str]:
    return {
        "kind": kind,
        "key": key,
        "field": field,
        "value": value,
        "observed_at": NOW,
        "availability": availability,
    }


def idle(brief: str = "Work.alpha", since: str = "2026-10-31T11:50:00Z") -> list[dict[str, str]]:
    return [fact("lemon", brief, "activity", "idle"), fact("lemon", brief, "idle_since", since)]


def snapshot(
    tasks: list[dict[str, str]], facts: list[dict[str, str]], **extra: ty.Any
) -> dict[str, ty.Any]:
    return {"name": "s1", "now": NOW, "tasks": tasks, "facts": facts, **extra}
