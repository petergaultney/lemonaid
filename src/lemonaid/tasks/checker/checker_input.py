"""A checker's view of one evaluate or describe input file."""

import datetime
import typing as ty

from . import protocol


class Fact(ty.NamedTuple):
    value: str
    observed_at: str
    availability: str


class View(ty.NamedTuple):
    context: dict[str, str]
    kind: str  # `task`, or `brief` for a working brief with no task
    subject: str  # its task ID or Lemon-ID, which its findings name
    fields: dict[str, str]
    cases: dict[str, dict[str, str]]
    facts: dict[tuple[str, str, str], Fact]


def read(text: str) -> View:
    """Raises protocol.ProtocolError for a malformed file, or one with other than one
    task or brief."""
    context: dict[str, str] = {}
    subjects: dict[tuple[str, str], dict[str, str]] = {}
    cases: dict[str, dict[str, str]] = {}
    facts: dict[tuple[str, str, str], Fact] = {}
    for record in protocol.parse(text, protocol.INPUT):
        match record:
            case ("context", field, value):
                context[field] = value
            case ("task" | "brief" as kind, subject, field, value):
                subjects.setdefault((kind, subject), {})[field] = value
            case ("case", case_id, field, value):
                cases.setdefault(case_id, {})[field] = value
            case ("fact", fact_kind, key, field, value, observed_at, availability):
                facts[(fact_kind, key, field)] = Fact(value, observed_at, availability)
    if len(subjects) != 1:
        raise protocol.ProtocolError(f"expected one task or brief, got {len(subjects)}")

    [((kind, subject), fields)] = subjects.items()
    return View(context, kind, subject, fields, cases, facts)


def timestamp(value: str) -> datetime.datetime:
    """An RFC3339 timestamp; raises ValueError for anything else, a naive time included."""
    parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{value!r} has no UTC offset")

    return parsed


def rfc3339(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
