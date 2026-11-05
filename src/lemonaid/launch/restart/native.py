"""Record process ownership from ordinary hooks, without inspecting native settings."""

import dataclasses
import os
import subprocess
from pathlib import Path

from ...claude import launch_args
from ...codex import channels
from ...inbox import db
from ...inbox.channel import channel_id
from ...log import get_logger
from ...messages import recipient
from . import process, state


def _observe(data: dict, harness: str) -> None:
    session = data.get("session_id") or data.get("thread_id") or data.get("thread-id")
    if not isinstance(session, str) or not session:
        return
    ancestors = process.ancestry(os.getppid())
    source = next((entry for entry in ancestors if recipient.is_harness(entry.executable)), None)
    if source is None or (Path(source.executable).name == "codex") != (harness == "codex"):
        return
    with db.connect() as conn:
        target = (
            channel_id(harness, session)
            if harness == "claude"
            else channels.for_session(conn, session)
        )
    state.write(
        "native-" + state.key(target) + ".json",
        {
            "session_id": session,
            "identity": dataclasses.asdict(source),
            "argv": launch_args.argv(source.pid),  # what restore carries over (`restore.carried`)
        },
    )


def binding(channel: str) -> dict | None:
    return state.read("native-" + state.key(channel) + ".json")


def recorded_argv(channel: str) -> list[str]:
    """The argv *channel*'s harness was last seen started with, [] when none was recorded."""
    found = (binding(channel) or {}).get("argv")
    return [str(arg) for arg in found] if isinstance(found, list) else []


def recovery_required(channel: str) -> bool:
    operation = state.latest(channel)
    if not operation or operation["phase"] != "partial":
        return False
    current = binding(channel)
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    return (
        not current
        or row is None
        or row.metadata.get("tty") != "/dev/" + current["identity"]["tty"]
        or current["identity"] == operation["plan"]["source"]
        or not process.same(process.Identity(**current["identity"]))
    )


def observe(data: dict, harness: str) -> None:
    try:
        _observe(data, harness)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        get_logger("restart.native").debug("Cannot record process ownership: %s", error)


def replacement(channel: str, original: dict) -> process.Identity | None:
    """The live process a hook recorded for *channel* since *original*, if any."""
    current = binding(channel)
    if not current or current["identity"] == original:
        return None
    source = process.Identity(**current["identity"])
    return source if process.same(source) else None


def resumed(channel: str, original: dict, root_pid: int) -> bool:
    source = replacement(channel, original)
    return source is not None and any(p.pid == root_pid for p in process.ancestry(source.pid))
