"""A stand-in for Claude Code: it leaves the traces lemonaid reads, then waits.

Started as `claude --session-id ID` or `claude --resume ID [PROMPT]`, it lists itself in
`$CLAUDE_CONFIG_DIR/sessions/<pid>.json`, writes a transcript and a history line, runs
every SessionStart hook in `$CLAUDE_CONFIG_DIR/settings.json`, and listens on its
messaging socket behind an empty composer. Resumed on a prompt, it first takes one turn on it: UserPromptSubmit
hooks, then Stop hooks. SIGUSR1 ends a turn: it runs the Stop hooks, as Claude does when it
finishes answering and waits for the user. Its session file is left behind when it is killed, as a crashed
Claude's is.

`$STAND_IN_DIR/<session id>.json` says where it really ran (pane, tty, pid, prompt), for
tests to check lemonaid against. `<session id>.turns` gets a line as each turn's Stop
hooks finish, and `<session id>.received` each message written to its socket.

`$STAND_IN_PYTHON` must be a link named `claude` to a Python interpreter. Linux names a
process for the file it executed, and lemonaid reads that name as well as `argv[0]`.
"""

import calendar
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

_START_FORMAT = "%a %b %d %H:%M:%S %Y"


def _session(args: list[str]) -> tuple[str, str, str]:
    """The session id, "resume" or "startup", and the first prompt ("" for none)."""
    for flag, source in (("--resume", "resume"), ("--session-id", "startup")):
        if flag in args and args.index(flag) + 1 < len(args):
            rest = args[args.index(flag) + 2 :]
            return args[args.index(flag) + 1], source, rest[-1] if rest else ""

    return str(uuid.uuid4()), "startup", ""


def _proc_start() -> str:
    """When this process started, in UTC, as Claude Code writes `procStart`."""
    local = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(os.getpid())],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "LC_ALL": "C"},
    ).stdout.strip()
    started = time.mktime(time.strptime(" ".join(local.split()), _START_FORMAT))
    return time.strftime(_START_FORMAT, time.gmtime(started))


def _hooks(config: Path, event: str) -> list[str]:
    try:
        settings = json.loads((config / "settings.json").read_text())
    except (OSError, ValueError):
        return []

    return [
        hook["command"]
        for entry in settings.get("hooks", {}).get(event, [])
        for hook in entry.get("hooks", [])
        if hook.get("type") == "command"
    ]


def main(args: list[str]) -> None:
    config = Path(os.environ["CLAUDE_CONFIG_DIR"])
    evidence = Path(os.environ["STAND_IN_DIR"])
    session_id, source, prompt = _session(args)
    cwd = os.getcwd()

    transcript = (
        config / "projects" / cwd.replace("/", "-").replace(".", "-") / f"{session_id}.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with transcript.open("a") as f:
        f.write(json.dumps({"type": "user", "cwd": cwd, "sessionId": session_id}) + "\n")
    with (config / "history.jsonl").open("a") as f:
        f.write(json.dumps({"sessionId": session_id, "project": cwd}) + "\n")

    path = evidence / f"{os.getpid()}.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen()

    sessions = config / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / f"{os.getpid()}.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "sessionId": session_id,
                "cwd": cwd,
                "messagingSocketPath": str(path),
                "procStart": _proc_start(),
                "startedAt": calendar.timegm(time.gmtime()) * 1000,
            }
        )
    )

    def run_hooks(event: str, **extra: str) -> None:
        hook_input = json.dumps(
            {
                "session_id": session_id,
                "cwd": cwd,
                "transcript_path": str(transcript),
                "hook_event_name": event,
                **extra,
            }
        )
        for command in _hooks(config, event):
            subprocess.run(command, shell=True, input=hook_input, text=True, check=False)

    def end_turn() -> None:
        run_hooks("Stop")
        with (evidence / f"{session_id}.turns").open("a") as turns:
            turns.write("turn\n")

    run_hooks("SessionStart", source=source)
    if prompt:
        run_hooks("UserPromptSubmit", prompt=prompt)
        end_turn()
    signal.signal(signal.SIGUSR1, lambda *_: end_turn())

    (evidence / f"{session_id}.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "pane": os.environ.get("TMUX_PANE", ""),
                "tty": os.ttyname(sys.stdin.fileno()),
                "prompt": prompt,
            }
        )
    )

    os.write(sys.stdout.fileno(), "\x1b[2J\x1b[H\u276f ".encode())  # Claude's empty composer
    while True:
        connection, _ = listener.accept()
        with connection, (evidence / f"{session_id}.received").open("ab") as received:
            while chunk := connection.recv(65536):
                received.write(chunk)


if __name__ == "__main__":
    main(sys.argv[1:])
