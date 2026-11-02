"""Task state as a fold over its events, so the `tasks` row can always be rebuilt from the log.

A state is a dict with the `tasks` table's columns. Events carry `event_id`, `revision`,
`kind`, `at` and `data`; every event advances the revision, including ones that change no
other column.
"""

import typing as ty
from collections import abc

State = dict[str, ty.Any]

Event = ty.Mapping[str, ty.Any]

COLUMNS = (
    "task_id",
    "description",
    "spec_brief_id",
    "sponsor",
    "subject_url",
    "holder",
    "previous_holder",
    "checker_id",
    "revision",
    "lifecycle",
    "assignment_event_id",
    "assigned_at",
    "attached_at",
    "created_at",
)


def _created(task_id: str, event: Event) -> State:
    data = event["data"]
    return {
        "task_id": task_id,
        "description": data["description"],
        "spec_brief_id": data["spec_brief_id"],
        "sponsor": data["sponsor"],
        "subject_url": data.get("subject_url", ""),
        "holder": data["holder"],
        "previous_holder": f"brief:{data['sponsor']}" if data["sponsor"] else "",
        "checker_id": data.get("checker_id", ""),
        "revision": event["revision"],
        "lifecycle": "open",
        "assignment_event_id": event["event_id"],
        "assigned_at": event["at"],
        "attached_at": event["at"] if data.get("attached") else None,
        "created_at": event["at"],
    }


def _changes(state: State, event: Event) -> State:
    data = event["data"]
    match event["kind"]:
        case "url_set":
            return {"subject_url": data["url"]}
        case "assigned":
            return {
                "holder": data["holder"],
                "previous_holder": state["holder"],
                "assignment_event_id": event["event_id"],
                "assigned_at": event["at"],
                "attached_at": event["at"] if data.get("attached") else None,
                "lifecycle": (
                    state["lifecycle"]
                    if state["lifecycle"] == "closed"
                    else "check"
                    if data.get("check")
                    else "open"
                ),
            }
        case "attached":
            return {"attached_at": state["attached_at"] or event["at"]}
        case "closed":
            return {"lifecycle": "closed"}
        case "reopened":
            return {"lifecycle": "open"}
        case "linked" | "unlinked" | "dependency_added" | "dependency_resolved" | "result":
            return {}
        case "acknowledged":  # recorded only by trial builds that had acknowledgment
            return {}
    raise ValueError(f"unknown task event {event['kind']!r}")


def apply(task_id: str, state: State | None, event: Event) -> State:
    if event["kind"] == "created":
        if state is not None:
            raise ValueError(f"task {task_id} was created twice")

        return _created(task_id, event)

    if state is None:
        raise ValueError(f"task {task_id} has {event['kind']} before created")

    if event["revision"] != state["revision"] + 1:
        raise ValueError(f"task {task_id} revision {event['revision']} after {state['revision']}")

    return {**state, **_changes(state, event), "revision": event["revision"]}


def fold(task_id: str, events: abc.Iterable[Event]) -> State | None:
    state = None
    for event in events:
        state = apply(task_id, state, event)
    return state
