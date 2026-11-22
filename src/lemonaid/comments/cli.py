"""`lemonaid comments`: read and write the comment threads kept in a Python or Markdown file.

The CLI makes each comment's id and timestamp and encodes its body, so a lemon never writes
the JSON itself. Commands that write refuse what the model refuses (see `edits`) and
leave the file as it was.

When an editor's `lemonaid lsp` has the file open with unsaved changes, a command that
writes sends its change to that server, which applies it to the buffer, and `list` reads
the buffer. Otherwise the command reads and writes the file.

    lemonaid comments list <path> [--unanswered --me <name>] [--resolved]
    lemonaid comments add <path> --lines <a>[-<b>] --as <name> <body | ->
    lemonaid comments reply <path> --re <id> --as <name> <body | ->
    lemonaid comments resolve <path> <id> --as <name>
    lemonaid comments strip <path>
"""

import argparse
import pathlib
import sys
import typing as ty

from .. import file
from ..front_end import location
from ..lsp import registry
from ..watch import signature
from . import edits, listing, model, notice, operations, parse

_ATTEMPTS: ty.Final = 3
_T = ty.TypeVar("_T")


class _Refused(Exception):
    pass


def _kind(target: pathlib.Path) -> model.FileKind:
    """The kind of `target`, a resolved path, so a link `notes.md` to `code.py` is Python."""
    kind = model.file_kind(str(target))
    if kind is None:
        raise _Refused("comments live only in Python (.py) and Markdown (.md) files")
    return kind


def _read(path: pathlib.Path) -> str:
    """The file's text with its line endings as they are, which edits must keep."""
    try:
        return path.read_bytes().decode()
    except FileNotFoundError:
        raise _Refused("no such file") from None
    except UnicodeDecodeError:
        raise _Refused("not UTF-8 text") from None


def _rewrite(
    target: pathlib.Path, change: ty.Callable[[str], tuple[str, _T]], *, retry: bool = True
) -> _T:
    """Apply `change` to the file, which returns the new text and what the command prints,
    and replace the file in one step, so an editor watching it never reads half of it.

    `target` is the resolved path: the command resolves a symlink once, so the link stays a
    link, the file it named changes, and the kind, the lock and the write all agree even if
    the link is retargeted meanwhile. If the
    file changes while we compute (an editor saves it), we don't overwrite that save: with
    `retry`, we start again from what the file holds now; without it, we refuse, for a
    change whose meaning the save may have moved. lemonaid's own writers take turns
    (`file.locked`), so they never lose each other's change. An editor that saves in the instant
    between our last check and the replace can still lose its save; the editor then holds
    it unsaved.
    """
    try:
        with file.locked(target):
            for _ in range(_ATTEMPTS):
                before = _read(target)
                after, result = change(before)
                if after == before:
                    return result
                if file.replace(
                    target, after, unless_changed_from=before, encoding="utf-8", newline=""
                ):
                    return result
                if not retry:
                    raise _Refused(
                        "the file changed while we wrote the comment, so its line numbers may"
                        " name other code now; check them and run the command again"
                    )
    except file.Busy as busy:
        raise _Refused(f"{busy}; try again in a moment") from None
    raise _Refused(f"the file kept changing while we wrote it; tried {_ATTEMPTS} times")


def _body(given: str) -> str:
    body = sys.stdin.read() if given == "-" else given
    if not body.strip():
        raise _Refused("the comment is empty")
    return body.rstrip("\n")


def _list(a: argparse.Namespace) -> int:
    unsaved = [buffer for buffer in _open_buffers(a.target) if buffer.state == "unsaved"]
    text = unsaved[0].text if unsaved else _read(a.target)
    doc = parse.parse(text, _kind(a.target))
    if a.unanswered and not a.me:
        raise _Refused(
            "--unanswered needs --me or --self, the names whose comments count as answers"
        )
    shown = listing.render(
        text,
        doc,
        unanswered_for=signature.forms(a.me) if a.unanswered else None,
        with_resolved=a.resolved,
    )
    if shown:
        print(shown)
    for error in listing.errors_text(text, doc):
        print(f"{a.path}: {error}", file=sys.stderr)
    return 1 if doc.errors else 0


def _add(a: argparse.Namespace) -> int:
    body = _body(a.body)
    comment_id = _carry_out(
        a.target, operations.Add(a.lines, a.author, body, a.quote or ""), retry=False
    )
    _tell_the_inbox(a, comment_id, body)
    print(comment_id)
    return 0


def _reply(a: argparse.Namespace) -> int:
    body = _body(a.body)
    comment_id = _carry_out(a.target, operations.Reply(a.re, a.author, body, a.after or ""))
    _tell_the_inbox(a, comment_id, body)
    print(comment_id)
    return 0


def _tell_the_inbox(a: argparse.Namespace, comment_id: str | None, body: str) -> None:
    """A lemon's comment (`--self`) shows in the inbox, under that lemon; a person's, written
    with `--as`, doesn't."""
    if a.use_self and comment_id:
        notice.replied(a.target, a.author, comment_id, body, _own_channel())


def _own_channel() -> str:
    """The calling lemon's inbox channel, or "" when nothing names it, which leaves its reply
    row under no lemon."""
    from ..brief import lemon
    from ..inbox import db

    with db.connect() as conn:
        try:
            return lemon.self_channel(conn)
        except LookupError:
            return ""


def own_signature(target: pathlib.Path) -> str:
    """The signature the calling lemon's watcher uses for `target`, read from its brief as
    the watcher reads it: a `watch doc` line for the file gives its `--me`, and a file the
    brief doesn't name gets `<name> (Author)`, as a Docs row does. A lemon that signs with
    it can't drift from the name its own waiter counts as answered."""
    from ..brief import command, identity
    from ..config import load_config
    from ..watch import subscriptions

    brief, error = command.own_brief(argparse.Namespace(session=None, channel=None, id=None))
    if brief is None:
        raise _Refused(f"--self: {error}")

    text = brief.read_text()
    vaults = tuple(load_config().brief.vaults)
    for spec in subscriptions.read(text, pathlib.Path.cwd(), vaults=vaults):
        if spec.kind == "doc" and pathlib.Path(spec.target[0]).resolve() == target.resolve():
            return spec.me

    try:
        name = identity.brief_name(identity.read(text))
    except ValueError:
        name = ""
    if not name:
        raise _Refused(f"--self: the brief {brief} has no Brief-ID to sign with")
    return f"{name} (Author)"


def _resolve(a: argparse.Namespace) -> int:
    _carry_out(a.target, operations.Resolve(a.id, a.author))
    return 0


def _strip(a: argparse.Namespace) -> int:
    _carry_out(a.target, operations.Strip())
    return 0


def _carry_out(
    target: pathlib.Path, operation: operations.Operation, *, retry: bool = True
) -> str | None:
    """Send `operation` to an editor whose buffer of the file has unsaved changes, or else
    write it to the file.

    A buffer without unsaved changes is left to the editor to reload, which it does without
    asking. We refuse while a buffer and the file have both changed since they last
    matched, since either write would leave them with different comments. An `add` that
    chose its lines from an unsaved buffer refuses if that buffer is saved, reverted or
    closed before the server writes, rather than anchor the same line numbers in the file.
    The server learns of your typing a moment after you type, so a write in that moment
    can still meet a buffer you have just changed; the editor then asks which version to
    keep.
    """
    kind = _kind(target)
    for buffer in _open_buffers(target):
        if buffer.state == "diverged":
            raise _Refused(_DIVERGED)
        if buffer.state != "unsaved":
            continue
        request: dict[str, ty.Any] = {
            "op": "apply",
            "path": str(target),
            "operation": operations.to_json(operation),
        }
        line_based = isinstance(operation, operations.Add)
        if line_based:
            request["observed"] = registry.text_digest(buffer.text)
        answer = registry.request(buffer.server, request)
        if "error" in answer:
            raise _Refused(answer["error"])
        if answer.get("open") and answer.get("state") == "unsaved":
            return answer.get("result")
        if line_based:
            raise _Refused(_MOVED)

    def change(text: str) -> tuple[str, str | None]:
        planned, result = operations.edits_for(operation, text, kind)
        return edits.apply(text, planned), result

    return _rewrite(target, change, retry=retry)


_DIVERGED: ty.Final = (
    "the file changed on disk since the editor's buffer last matched it; ask the user"
    " to save or reload the file, then try again"
)
_MOVED: ty.Final = (
    "the editor's buffer changed while we wrote the comment, so its line numbers may name"
    " other code now; check them and run the command again"
)


class _Buffer(ty.NamedTuple):
    server: registry.Record
    text: str
    state: str  # `clean`, `unsaved` or `diverged`, see the server's `_state`


def _open_buffers(target: pathlib.Path) -> list[_Buffer]:
    """The editor buffers that hold the file, those that have diverged from it or have
    unsaved changes first. A server that doesn't answer is passed over."""
    buffers = []
    for server in registry.by_preference(registry.live(), location.here()):
        try:
            answer = registry.request(server, {"op": "buffer", "path": str(target)})
        except registry.Unreachable:
            continue
        text, state = answer.get("text"), answer.get("state")
        if answer.get("open") and isinstance(text, str) and isinstance(state, str):
            buffers.append(_Buffer(server, text, state))
    order = {"diverged": 0, "unsaved": 1}
    return sorted(buffers, key=lambda b: order.get(b.state, 2))


def _run(a: argparse.Namespace) -> ty.NoReturn:
    try:
        a.target = a.path.resolve()
        if getattr(a, "use_self", False):
            signed = own_signature(a.target)
            if a.comments_func is _list:
                a.me = [*a.me, signed]
            else:
                a.author = signed
        code = a.comments_func(a)
    except (_Refused, ValueError, registry.Unreachable) as refusal:
        print(f"{a.path}: {refusal}", file=sys.stderr)
        code = 2
    sys.exit(code)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    ap = subparsers.add_parser(
        "comments",
        help="read and write the comment threads kept in a Python or Markdown file",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="comments_command", required=True)

    listing_parser = sub.add_parser("list", help="print the file's threads with their code")
    listing_parser.add_argument("path", type=pathlib.Path)
    listing_parser.add_argument(
        "--unanswered", action="store_true", help="only threads with a comment waiting on --me"
    )
    listing_parser.add_argument(
        "--me", action="append", default=[], help="your name or signature; repeat for old names"
    )
    listing_parser.add_argument(
        "--resolved", action="store_true", help="include resolved threads and branches"
    )
    listing_parser.set_defaults(comments_func=_list)

    add = sub.add_parser("add", help="anchor a new thread on lines and write its first comment")
    add.add_argument("path", type=pathlib.Path)
    add.add_argument("--lines", required=True, help="<a>-<b> or <a>, 1-based and inclusive")
    add.set_defaults(comments_func=_add)

    reply = sub.add_parser("reply", help="answer a comment")
    reply.add_argument("path", type=pathlib.Path)
    reply.add_argument("--re", required=True, help="the id of the comment you answer")
    reply.set_defaults(comments_func=_reply)

    resolve = sub.add_parser("resolve", help="resolve a comment and every reply below it")
    resolve.add_argument("path", type=pathlib.Path)
    resolve.add_argument("id")
    resolve.set_defaults(comments_func=_resolve)

    strip = sub.add_parser("strip", help="remove every comment from the file")
    strip.add_argument("path", type=pathlib.Path)
    strip.set_defaults(comments_func=_strip)

    add.add_argument(
        "--quote", help="anchor on this text within the lines (Markdown only), not the whole lines"
    )
    reply.add_argument(
        "--after",
        help="the newest reply to --re you have read; needed once it has replies, so you don't"
        " repeat an answer someone just gave",
    )
    listing_parser.add_argument(
        "--self",
        dest="use_self",
        action="store_true",
        help="count the signature your watcher uses for this file as yours",
    )
    for parser in (add, reply):
        parser.add_argument("body", help="Markdown; - reads it from stdin")
    for parser in (add, reply, resolve):
        who = parser.add_mutually_exclusive_group(required=True)
        who.add_argument(
            "--as", dest="author", help="your signature, as in Relay: `SleepRib (Author)`"
        )
        who.add_argument(
            "--self",
            dest="use_self",
            action="store_true",
            help="sign with the signature your watcher uses for this file",
        )
    ap.set_defaults(func=_run)
