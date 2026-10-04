"""Delivery adapters: how a waiter hands one event to the lemon it wakes.

Event detection (doc_events.py) never knows which harness it is waking. Each adapter takes
the event message and either delivers it or raises `Failed`; a waiter records an event as
reported only after its delivery succeeds.
"""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import typing as ty

Deliver = ty.Callable[[str], None]


class Failed(Exception):
    pass


def to_stdout(message: str) -> None:
    print(message, flush=True)


def codex_setup_problem() -> str:
    """Why `codex queue` would fail from this process, or "" - checked before waiting, not at the first event."""
    if not shutil.which("codex"):
        return "`codex` is not on PATH"

    probe = (
        pathlib.Path(os.environ.get("CODEX_HOME", pathlib.Path.home() / ".codex"))
        / f".watch-probe-{os.getpid()}"
    )
    try:
        probe.touch()
        probe.unlink()
    except OSError as e:
        return f"cannot write {probe.parent} ({e}), so `codex queue` would fail; run the waiter outside the sandbox"
    return ""


def add_codex_thread_argument(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--codex-thread",
        nargs="?",
        const=None,
        default="",
        metavar="THREAD_ID",
        help="queue one event into this Codex thread (bare: $CODEX_THREAD_ID) and exit instead of printing events forever",
    )


def codex_thread(arg: str | None) -> tuple[str, str]:
    """(thread, problem) for `--codex-thread`: its value, or this process's own thread when given bare.

    The bare form keeps `$CODEX_THREAD_ID` out of the command line: Codex matches its
    allow rules only against commands without shell expansions.
    """
    if arg is not None:
        return arg, ""

    thread = os.environ.get("CODEX_THREAD_ID", "")
    return thread, "" if thread else "--codex-thread without a THREAD_ID needs CODEX_THREAD_ID set"


def to_codex(thread: str, kind: str, instruction: str) -> Deliver:
    """Queues `<kind> event: <message>. <instruction>` into a Codex thread."""

    def deliver(message: str) -> None:
        try:
            subprocess.run(
                [
                    "codex",
                    "queue",
                    "--thread",
                    thread,
                    "--message",
                    f"{kind} event: {message}. {instruction}",
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise Failed(f"codex queue failed ({e})") from e

    return deliver


def openclaw_setup_problem(cli: str) -> str:
    return "" if shutil.which(cli) else f"`{cli}` is not on PATH"


def _last_json(stdout: str) -> dict[str, ty.Any] | None:
    """The CLI's JSON result: all of stdout, or else its last line that parses (it may print a banner first)."""
    for candidate in [stdout, *reversed(stdout.splitlines())]:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def to_openclaw(session_key: str, me: str, hq_session: str, cli: str, timeout_ms: int) -> Deliver:
    """Runs one agent turn in `session_key` and waits for it to finish.

    The idempotency key is derived from the message, so re-sending an event after a timeout
    that did reach the gateway does not start a second turn.
    """

    def deliver(message: str) -> None:
        text = "\n".join(
            [
                f"watch-doc event: {message}",
                "",
                "Use the watch-doc skill: re-read the document and reply inline to every unanswered Relay Comment thread,",
                f'signing each reply block author="{me}" authorId="{session_key}".',
                "This turn only answers comments: do not refile or move anything, and do not message the user directly.",
                f"If something needs the user outside the document, hand it to the user's session with sessions_send to {hq_session}.",
            ]
        )
        params = {
            "message": text,
            "sessionKey": session_key,
            "idempotencyKey": hashlib.sha1(f"{session_key}\0{message}".encode()).hexdigest(),
        }
        cp = subprocess.run(
            [
                cli,
                "gateway",
                "call",
                "agent",
                "--json",
                "--expect-final",
                "--params",
                json.dumps(params),
                "--timeout",
                str(timeout_ms),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode != 0:
            raise Failed(
                f"openclaw gateway call agent exited {cp.returncode}: {(cp.stderr or cp.stdout).strip()[-500:]}"
            )

        result = _last_json(cp.stdout)
        if result is None:
            raise Failed(f"openclaw gateway call agent printed no JSON: {cp.stdout.strip()[-500:]}")
        if result.get("ok") is False or result.get("status") == "error":
            raise Failed(f"openclaw agent turn failed: {json.dumps(result)[-500:]}")

    return deliver
