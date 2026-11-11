"""What restore will do for each lost lemon: where it goes and the line that resumes it.

Pure apart from reading briefs, transcripts and recorded launch flags: nothing is
started, so `--dry-run` shows the plan as it would run.
"""

import time
import typing as ty
from collections import abc
from pathlib import Path

from ..claude import session_socket
from ..codex import channels, utils
from ..config import Config
from ..inbox import db, ended
from . import carried, launch, prompt, report, run


class Plan(ty.NamedTuple):
    lemons: list[run.Lemon]  # in the order to start them
    skipped: list[report.Result]  # lost lemons restore can't start, and why


def transcript_missing(row: db.Notification) -> bool:
    """Whether the conversation a resume would reopen is gone, so a resume would start an
    empty one under the lemon's name."""
    harness = row.channel.partition(":")[0]
    if harness == "claude":
        session = str(row.metadata.get("session_id") or "")
        return not session or not any(
            session_socket.claude_dir().glob(f"projects/*/{session}.jsonl")
        )

    if harness == "codex":
        return utils.find_session_path(channels.owner_id(row.channel, row.metadata, {})) is None

    return False


def _skipped(row: db.Notification, why: str) -> report.Result:
    return report.Result(row.channel, row.name or row.channel, "", report.NOT_RESTORED, why)


class Brief(ty.NamedTuple):
    lemon_id: str
    text: str
    path: Path


def build(
    rows: abc.Iterable[db.Notification],
    place: abc.Callable[
        [abc.Iterable[db.Notification]],
        tuple[list[tuple[db.Notification, run.Spot]], list[tuple[db.Notification, str]]],
    ],
    config: Config,
    briefs: abc.Mapping[str, Brief],
    flags: abc.Callable[[str], list[str]],
) -> Plan:
    """The plan for lost *rows*, given where their front end places them, each channel's
    brief, and the launch argv recorded for a channel (`flags`)."""
    startable: list[tuple[db.Notification, launch.Launch]] = []
    skipped: list[report.Result] = []
    for row in rows:
        harness = row.channel.partition(":")[0]
        resumed = launch.launch(row, config, "", flags=carried.flags(harness, flags(row.channel)))
        if resumed is None:
            skipped.append(_skipped(row, "no working directory or resume command is recorded"))
        elif transcript_missing(row):
            skipped.append(_skipped(row, "its conversation's transcript is gone"))
        else:
            startable.append((row, resumed))

    launches = {row.channel: resumed for row, resumed in startable}
    placed, unplaced = place(row for row, _ in startable)
    skipped += [_skipped(row, why) for row, why in unplaced]
    lemons: list[run.Lemon] = []
    for row, spot in placed:
        harness = row.channel.partition(":")[0]
        resumed = launches[row.channel]
        brief = briefs.get(row.channel)
        lost_at = float((row.metadata.get(ended.KEY) or {}).get("at") or time.time())
        lemons.append(
            run.Lemon(
                row,
                spot,
                resumed,
                brief.lemon_id if brief else "",
                prompt.rearm(brief.path, brief.text, harness) if brief else "",
                prompt.lost_terminal(lost_at)
                if brief and prompt.interrupted(brief.lemon_id, brief.text)
                else "",
            )
        )
    return Plan(lemons, skipped)


NOTHING = "Nothing to restore: no lemon was lost with its terminal."


def describe(plan: Plan) -> list[str]:
    """The plan as lines, for a person deciding whether to run it."""
    if not plan.lemons and not plan.skipped:
        return [NOTHING]

    return [
        *(
            f"{lemon.spot.where:<24} {lemon.row.name or lemon.channel} ({lemon.launch.cwd})"
            + (f"  [was {lemon.spot.was}]" if lemon.spot.was else "")
            for lemon in plan.lemons
        ),
        *(f"{'not restored':<24} {r.name}  ({r.detail})" for r in plan.skipped),
    ]


def as_json(plan: Plan) -> list[dict]:
    return [
        {
            "channel": lemon.channel,
            "name": lemon.row.name or lemon.channel,
            "where": lemon.spot.where,
            "was": lemon.spot.was,
            "cwd": lemon.launch.cwd,
            "line": lemon.launch.line,
            "brief": bool(lemon.lemon_id),
        }
        for lemon in plan.lemons
    ]
