"""Record restartable watches in the caller's attached brief, across one-shot rearms."""

import argparse
import fcntl
import hashlib
import pathlib
import shlex
import tempfile
from collections import abc

from ..brief import attached, identity, lemon, store, verbs_cli, waiters
from ..inbox import db
from ..inbox.channel import full_channel_id
from . import record_context, registry


class _WatchParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise ValueError(message or "not a watch invocation")


def _identity(
    command: str, owner: str = "", repo: str = "", cwd: pathlib.Path | None = None
) -> tuple | None:
    # Use the actual CLI grammar so unknown arguments and shell operations cannot
    # be mistaken for an automatic entry. Import lazily: each CLI records itself.
    from . import briefs_cli, doc_cli, file_cli, pr_cli

    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer)
        if words[:2] != ["lemonaid", "watch"] or any(
            word in ("--help", "-h") or all(c in ";&|<>()" for c in word) for word in words
        ):
            return None
        parser = _WatchParser(allow_abbrev=False)
        sub = parser.add_subparsers(required=True)
        for module in (doc_cli, pr_cli, file_cli, briefs_cli):
            module.add_parser(sub)
        a = parser.parse_args(words[2:])
    except ValueError:
        return None
    kind = words[2]
    if a.status or getattr(a, "editing", None) or getattr(a, "mine", None):
        return None
    if kind == "briefs":
        parent = owner if a.use_self else a.lemon
        if not parent:
            return None  # preserve an old --self command when its owner is unknown
        target = (parent,)
    elif kind == "pr":
        target = (str(a.wait),)
        if not a.repo and not repo:
            return None
    else:
        paths = a.wait if kind == "file" else [a.wait or a.watch_list]
        expanded = [p.expanduser() for p in paths]
        if cwd is None and any(not p.is_absolute() for p in expanded):
            return None
        target = tuple(
            sorted({str((p if p.is_absolute() else cwd / p).resolve()) for p in expanded})
        )
    return (
        kind,
        bool(getattr(a, "watch_list", None)),
        target,
        getattr(a, "repo", "") or repo,
        a.me,
        tuple(sorted(set(a.to or ("merge", "done")))) if kind == "briefs" else (),
    )


def _same_watch(
    text: str, command: str, repo: str, cwd: pathlib.Path, contexts: record_context.Contexts
) -> abc.Callable[[str], bool]:
    """Whether a listed command is the same watch as *command*, run in *cwd*."""
    try:
        owner = identity.read(text)
    except ValueError:
        owner = ""
    key = _identity(command, owner, repo, cwd)

    def same(old: str) -> bool:
        saved = contexts.get(old, [])
        keys = [
            _identity(old, owner, item["repo"], pathlib.Path(item["cwd"])) for item in saved
        ] or [_identity(old, owner)]
        return key is not None and all(old_key == key for old_key in keys)

    return same


def _upsert(
    text: str, command: str, repo: str = "", contexts: record_context.Contexts | None = None
) -> str:
    return waiters.upsert(
        text, command, _same_watch(text, command, repo, pathlib.Path.cwd(), contexts or {})
    )


def _is_inbox_watch(command: str) -> bool:
    try:
        return shlex.split(command)[:3] == ["lemonaid", "inbox", "watch"]
    except ValueError:
        return False


def _context_path(path: pathlib.Path) -> pathlib.Path:
    return path.with_name(f".{path.name}.waiter-context.json")


def forget(path: pathlib.Path, stopped: abc.Sequence[registry.Waiter]) -> str:
    """An error, or "" once each *stopped* waiter's entry is gone from *path*'s `## Waiters`."""
    contexts = record_context.load(_context_path(path))

    def change(text: str) -> str:
        sames = [
            _is_inbox_watch
            if w.kind == "inbox"
            else _same_watch(text, w.command, w.repo, pathlib.Path(w.cwd), contexts)
            for w in stopped
        ]
        commands = {w.command for w in stopped}
        return waiters.remove_where(
            text, lambda old: old in commands or any(same(old) for same in sames)
        )

    return verbs_cli.edit(path, change, preserve_existing=True)


def record(a: argparse.Namespace, kind: str, thread: str = "", repo: str = "") -> str:
    """An error or ""; a caller without an attached brief keeps ordinary watch behavior."""
    with db.connect() as conn:
        try:
            channel = (
                full_channel_id("codex", thread)
                if thread
                else lemon.self_channel(conn, getattr(a, "channel", "") or "")
            )
        except LookupError:
            return ""
        attached.claim_pending(conn)
        row = conn.execute(
            "SELECT path FROM session_briefs WHERE channel = ?", (channel,)
        ).fetchone()
    if row is None:
        return ""
    path = pathlib.Path(row["path"])
    if error := store.outside_error(path):
        return error

    invocation = getattr(a, "invocation", None)
    if not invocation or invocation[:3] != ["lemonaid", "watch", kind]:
        return ""  # Only a CLI invocation has an original command to record.
    command = shlex.join(invocation)

    # Several independent watches can start together for one brief. Serialize their
    # edits without deleting the lock file underneath another waiting process.
    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    directory = pathlib.Path(tempfile.gettempdir()) / "lemonaid-brief-waiters"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / key).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            context_path = _context_path(path)
            contexts = record_context.load(context_path)
            error = verbs_cli.edit(
                path, lambda text: _upsert(text, command, repo, contexts), preserve_existing=True
            )
            if error:
                return error

            present = waiters.commands(path.read_text())
            contexts = {old: saved for old, saved in contexts.items() if old in present}
            current = {"cwd": str(pathlib.Path.cwd()), "repo": repo}
            saved = contexts.setdefault(command, [])
            if current not in saved:
                saved.append(current)
            record_context.save(context_path, contexts)
            return ""
    except (OSError, ValueError) as error:
        return str(error)
