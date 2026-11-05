"""Read-only checks before a move: the process to stop, and the resume its front end will run."""

import dataclasses
import shlex
from pathlib import Path

from ...brief import identity, lemon
from ...claude import launch_args, trust
from ...config import Config
from ...front_end import location, pick
from ...inbox import db
from ...restore import launch
from ...resume import build_resume_command
from .. import command
from ..restart import native, process, state
from ..restart.planning import idle
from .destination import Destination

PROMPT = (
    "You were just moved to {directory} and resumed in the same native session there. "
    "Keep your existing task and brief; your working directory is now {directory}. "
    "Rearm any watchers or other transient state you need to manage, read your pending "
    "mailbox messages, and continue your existing work."
)


def _location_patch(destination: Destination, workspace_key: str) -> dict[str, str]:
    """The recorded location a lemon has once it is at *destination*."""
    return {
        "cwd": destination.directory,
        **({workspace_key: destination.workspace} if workspace_key else {}),
    }


def moved(row: db.Notification, patch: dict[str, str]) -> db.Notification:
    return dataclasses.replace(row, metadata={**row.metadata, **patch})


def build(conn, target: str, destination: Destination, config: Config, force: bool = False) -> dict:
    attached = lemon.attachment(conn, target, claim_pending=False)
    row = attached.notification
    if row is None or row.is_archived:
        raise ValueError(
            state.inspection(attached.channel)
            or "The lemon has no live row; bring it back with `lemonaid lemon resume`, then move it"
        )

    if row.channel.partition(":")[0] not in ("claude", "codex"):
        raise ValueError("Move supports Claude and Codex sessions")

    idle(row, force)
    where = location.of(row.metadata, row.switch_source)
    if where.front_end != destination.front_end:
        raise ValueError("The lemon's terminal changed since its destination was chosen")

    found = pick.named(where.front_end)
    if found is None or found.start is None:
        raise ValueError(f"lemonaid can't start a lemon in {where.front_end or 'its terminal'}")

    if Path(str(row.metadata.get("cwd") or "")).resolve() == Path(destination.directory):
        raise ValueError(f"The lemon already works in {destination.directory}")

    claude_trust = row.channel.startswith("claude:") and not trust.trusted(
        Path(destination.directory), trust.config_file()
    )
    root = config.places.root_for(destination.directory)
    if claude_trust and (root is None or not root.claude_trust):
        raise ValueError(
            f"Claude doesn't trust {destination.directory} yet, so the resumed lemon would stop "
            "at its folder-trust prompt. Start Claude there once and accept the prompt, or set "
            "claude_trust on its places root, then move the lemon"
        )

    recorded = native.binding(row.channel)
    if not recorded or recorded["session_id"] != row.metadata.get("session_id"):
        raise ValueError(
            "No process binding for this native session; obtain a fresh hook observation"
        )

    source = process.Identity(**recorded["identity"])
    if not process.same(source) or row.metadata.get("tty") != "/dev/" + source.tty:
        raise ValueError("The native process no longer owns the recorded terminal")

    if reason := command.unclaimable(shlex.join(launch_args.argv(source.pid))):
        raise ValueError(reason)

    patch = _location_patch(destination, found.terminal.workspace_key)
    prompt = PROMPT.format(directory=destination.directory)
    planned = launch.launch(moved(row, patch), config, prompt)
    if planned is None or not planned.prompted or planned.cwd != destination.directory:
        raise ValueError(
            "The configured resume command cannot resume in the destination with move instructions"
        )

    # The planned line is wrapped in `env`, so check the command the front end will run.
    resumable = build_resume_command(config, row.channel, moved(row, patch).metadata)
    if resumable and (reason := command.unclaimable(shlex.join(resumable[1]))):
        raise ValueError(reason)

    return {
        "kind": "move",
        "channel": row.channel,
        "lemon_id": identity.from_path(attached.path),
        "source": dataclasses.asdict(source),
        "from": {
            "cwd": str(row.metadata.get("cwd") or ""),
            "workspace": where.workspace,
            "instance": where.instance,
            "tty": where.tty,
        },
        "destination": dataclasses.asdict(destination),
        "patch": patch,
        "prompt": prompt,
        "line": planned.line,
        "environment": planned.environment,
        "cwd": planned.cwd,
        "force": force,
        "claude_trust": claude_trust,  # record Claude's trust in the destination before the stop
    }
