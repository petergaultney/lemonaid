"""`lemonaid watch openclaw`: start, stop, or list OpenClaw doc watches.

Each OpenClaw session is one actor with one watch list and at most one waiter, a
transient systemd user unit running `lemonaid watch doc --watch-list` from the same
Python as this command. Starting a watch removes the doc from every other session's
list, so a comment wakes the session that wrote the doc most recently. Lists are shared
with the standalone openclaw_watch.py, so a waiter started by either serves both.

    lemonaid watch openclaw start <doc> --session-key agent:main:doc-filing-worker-v2:<run_id> --me <name>
    lemonaid watch openclaw stop <doc>
    lemonaid watch openclaw list
"""

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import uuid

from . import watch_list

_LIST_PREFIX = "openclaw-"
_DAY = 86_400


def _unit_path() -> str:
    """openclaw is a node script, and non-interactive shells on its host don't load mise."""
    home = pathlib.Path.home()
    return ":".join(
        [
            str(home / ".local/share/mise/shims"),
            str(home / ".local/bin"),
            "/usr/local/bin:/usr/bin:/bin",
        ]
    )


def list_path(lists_dir: pathlib.Path, session_key: str) -> pathlib.Path:
    return lists_dir / f"{_LIST_PREFIX}{hashlib.sha1(session_key.encode()).hexdigest()[:12]}.json"


def _session_lists(lists_dir: pathlib.Path) -> list[pathlib.Path]:
    return sorted(lists_dir.glob(f"{_LIST_PREFIX}*.json"))


def _session_key(path: pathlib.Path) -> str:
    try:
        return json.loads(path.with_suffix(".session").read_text())["session_key"]
    except (OSError, ValueError, KeyError):
        return "?"


def waiter_command(
    target: pathlib.Path, session_key: str, me: str, hq_session: str, idle_days: float
) -> list[str]:
    return [
        "systemd-run",
        "--user",
        "--collect",
        f"--unit=watch-doc-{target.stem}-{uuid.uuid4().hex[:8]}",  # a second waiter started in a race exits at once
        f"--description=watch-doc for OpenClaw session {session_key}",
        f"--setenv=PATH={_unit_path()}",
        sys.executable,
        "-m",
        "lemonaid",
        "watch",
        "doc",
        "--watch-list",
        str(target),
        "--me",
        me,
        "--openclaw-session",
        session_key,
        "--hq-session",
        hq_session,
        "--idle-expire",
        str(int(idle_days * _DAY)),
    ]


def start(
    lists_dir: pathlib.Path,
    doc: pathlib.Path,
    session_key: str,
    me: str,
    hq_session: str,
    idle_days: float,
) -> None:
    target = list_path(lists_dir, session_key)
    for other in _session_lists(lists_dir):
        if other != target:
            watch_list.remove(other, doc)
    lists_dir.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".session").write_text(json.dumps({"session_key": session_key}))
    if watch_list.add(target, doc):
        subprocess.run(waiter_command(target, session_key, me, hq_session, idle_days), check=True)


def stop(lists_dir: pathlib.Path, doc: pathlib.Path) -> None:
    for path in _session_lists(lists_dir):
        if watch_list.remove(path, doc):
            print(f"stopped watching {doc} for {_session_key(path)}")


def show(lists_dir: pathlib.Path) -> None:
    now = time.time()
    for path in _session_lists(lists_dir):
        for doc, last in watch_list.read(path).items():
            print(f"{_session_key(path)}\t{(now - last) / _DAY:.1f}d idle\t{doc}")


def _author_name(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("must not be blank")

    return value


def _cmd(a: argparse.Namespace) -> None:
    lists_dir = watch_list.default_lists_dir()
    if a.openclaw_command == "start":
        start(lists_dir, a.doc, a.session_key, a.me, a.hq_session, a.idle_days)
    elif a.openclaw_command == "stop":
        stop(lists_dir, a.doc)
    else:
        show(lists_dir)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "openclaw",
        help="Start, stop, or list doc watches for OpenClaw sessions",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="openclaw_command", required=True)
    start_p = sub.add_parser(
        "start", help="watch a doc for a session, taking it from any other session"
    )
    start_p.add_argument("doc", type=pathlib.Path)
    start_p.add_argument(
        "--session-key", required=True, help="the OpenClaw session a comment wakes"
    )
    start_p.add_argument(
        "--me",
        required=True,
        type=_author_name,
        help="author name the session signs replies with",
    )
    start_p.add_argument(
        "--hq-session",
        default="agent:main:main",
        help="where a woken turn escalates to the human",
    )
    start_p.add_argument(
        "--idle-days",
        type=float,
        default=7.0,
        help="drop the doc after this many days with no comment",
    )
    stop_p = sub.add_parser("stop", help="stop watching a doc")
    stop_p.add_argument("doc", type=pathlib.Path)
    sub.add_parser("list", help="list watched docs by session")
    ap.set_defaults(func=_cmd)
