"""Read-only checks of the process and pane that a configured resume will replace."""

import dataclasses
import os
import shlex

from ...brief import identity, lemon
from ...claude import launch_args
from ...config import Config
from ...inbox import db
from ...launch import command
from ...messages import recipient
from ...restore import launch
from ...watch import registry
from . import native, pane, process

PROMPT = (
    "You were just restarted in the same native session. Keep your existing task and brief. "
    "Rearm any watchers or other transient state you need to manage, read your pending inbox "
    "messages, and continue your existing work."
)


def idle(row: db.Notification, force: bool) -> None:
    if not force and (row.asks or row.turn_at is not None):
        raise ValueError("The lemon is mid-turn or asking for input; use --force to interrupt it")


def build(conn, target: str, config: Config, force: bool = False) -> dict:
    attached = lemon.attachment(conn, target, claim_pending=False)
    row = attached.notification
    if row is None or row.is_archived:
        raise ValueError("The lemon has no live row; use lemon resume")
    if row.channel.partition(":")[0] not in ("claude", "codex"):
        raise ValueError("Restart supports Claude and Codex sessions")
    idle(row, force)
    target_pane = pane.locate(
        str(row.metadata.get("tmux_socket") or ""), str(row.metadata.get("tty") or "")
    )
    if target_pane.dead or target_pane.cwd != row.metadata.get("cwd"):
        raise ValueError("The live pane and recorded directory disagree")
    recorded = native.binding(row.channel)
    if not recorded or recorded["session_id"] != row.metadata.get("session_id"):
        raise ValueError(
            "No process binding for this native session; obtain a fresh hook observation"
        )
    source = process.Identity(**recorded["identity"])
    root = process.inspect(target_pane.pid)
    lineage = process.ancestry(source.pid)
    if (
        root is None
        or root not in lineage
        or not process.same(source)
        or source.tty != target_pane.tty.removeprefix("/dev/")
    ):
        raise ValueError("The native process no longer owns the recorded pane")
    if sum(recipient.is_harness(p.executable) for p in lineage[: lineage.index(root) + 1]) != 1:
        raise ValueError("Multiple harnesses share the terminal ancestry")
    if reason := command.unclaimable(shlex.join(launch_args.argv(source.pid))):
        raise ValueError(reason)
    planned = launch.launch(row, config, PROMPT, dedicated=True)
    if planned is None or not planned.prompted or planned.cwd != target_pane.cwd:
        raise ValueError(
            "The configured resume command cannot resume here with restart instructions"
        )
    caller = process.ancestry(os.getpid())
    own_chain = caller[: caller.index(source)] if source in caller else []
    waiters = registry.mine(row.channel)
    allowed = {p.pid for p in lineage + own_chain} | {w.pid for w in waiters}
    # Children may be native helpers or tools: do not infer their purpose or signal them.
    # The harness owns their shutdown; all must leave the TTY before pane replacement.
    descendants = process.descendants(source.pid)
    if any(p.pid not in allowed and p not in descendants for p in process.on_tty(target_pane.tty)):
        raise ValueError("Unrelated jobs share the terminal")
    return {
        "channel": row.channel,
        "lemon_id": identity.from_path(attached.path),
        "pane": dataclasses.asdict(target_pane),
        "source": dataclasses.asdict(source),
        "root": dataclasses.asdict(root),
        "line": planned.line,
        "environment": planned.environment,
        "cwd": planned.cwd,
        "force": force,
        "exit_option": pane.exit_option(target_pane),
    }
