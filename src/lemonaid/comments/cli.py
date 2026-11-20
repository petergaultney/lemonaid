"""`lemonaid comments`: read and write the comment threads kept in a Python or Markdown file.

The CLI makes each comment's id and timestamp and encodes its body, so a lemon never writes
the JSON itself. Commands that write refuse what the model refuses (see `edits`) and
leave the file as it was.

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
from ..watch import signature
from . import edits, listing, model, parse

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


def _line_range(text: str, lines: str) -> tuple[int, int]:
    """`a-b` or `a` (1-based, inclusive) as offsets from the start of line a to the end of
    line b's text, before its own line ending. The empty "line" after a file's last line
    ending is not a line."""
    first_text, _, last_text = lines.partition("-")
    try:
        first, last = int(first_text), int(last_text or first_text)
    except ValueError:
        raise _Refused(f"--lines {lines}: expected <a>-<b> or <a>") from None
    starts = listing.line_starts(text)
    line_count = len(starts) - (starts[-1] == len(text))
    if not 1 <= first <= last <= line_count:
        raise _Refused(f"--lines {lines}: the file has {line_count} line(s)")
    last_line_end = starts[last] if last < len(starts) else len(text)
    last_line_text = text[starts[last - 1] : last_line_end].rstrip("\r\n")
    return starts[first - 1], starts[last - 1] + len(last_line_text)


def _list(a: argparse.Namespace) -> int:
    text = _read(a.target)
    doc = parse.parse(text, _kind(a.target))
    if a.unanswered and not a.me:
        raise _Refused("--unanswered needs --me, the names whose comments count as answers")
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
    kind, body = _kind(a.target), _body(a.body)

    def add(text: str) -> tuple[str, str]:
        start, end = _line_range(text, a.lines)
        added = edits.add_comment(text, kind, start, end, author=a.author, body=body)
        return edits.apply(text, added.edits), added.comment_id

    print(_rewrite(a.target, add, retry=False))
    return 0


def _reply(a: argparse.Namespace) -> int:
    kind, body = _kind(a.target), _body(a.body)

    def reply(text: str) -> tuple[str, str]:
        added = edits.reply(text, kind, a.re, author=a.author, body=body)
        return edits.apply(text, added.edits), added.comment_id

    print(_rewrite(a.target, reply))
    return 0


def _resolve(a: argparse.Namespace) -> int:
    kind = _kind(a.target)

    def resolve(text: str) -> tuple[str, None]:
        return edits.apply(text, [edits.resolve(text, kind, a.id, author=a.author)]), None

    _rewrite(a.target, resolve)
    return 0


def _strip(a: argparse.Namespace) -> int:
    kind = _kind(a.target)
    _rewrite(a.target, lambda text: (edits.strip(text, kind), None))
    return 0


def _run(a: argparse.Namespace) -> ty.NoReturn:
    try:
        a.target = a.path.resolve()
        code = a.comments_func(a)
    except (_Refused, ValueError) as refusal:
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

    for parser in (add, reply):
        parser.add_argument("body", help="Markdown; - reads it from stdin")
    for parser in (add, reply, resolve):
        parser.add_argument(
            "--as",
            dest="author",
            required=True,
            help="your signature, as in Relay: `SleepRib (Author)`",
        )
    ap.set_defaults(func=_run)
