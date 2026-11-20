"""`lemonaid lsp`, which an editor starts, and `lemonaid editor`, through which a lemon reaches
the editor that started it.

    lemonaid lsp
    lemonaid editor open <path> [--line <n>] [--focus]
    lemonaid editor notify <message>
"""

import argparse
import pathlib
import sys
import typing as ty

from . import registry

_INSTALL_HINT: ty.Final = (
    "`lemonaid lsp` needs the `lsp` extra: install lemonaid as `lemonaid-inbox[lsp]`"
    " (for an editable install, `uv tool install -e '.[lsp]'`)"
)


class _NoEditor(Exception):
    pass


def _lsp(_: argparse.Namespace) -> None:
    try:
        from . import server
    except ImportError:
        print(_INSTALL_HINT, file=sys.stderr)
        sys.exit(2)
    server.main()


def _open(a: argparse.Namespace) -> None:
    target = a.path.resolve()
    if a.line is not None and a.line < 1:
        raise _NoEditor("--line counts from 1")
    covering = [record for record in registry.live() if record.covers(target)]
    if not covering:
        raise _NoEditor(f"no editor server has a workspace that holds {a.path}")
    answer = _ask(covering, {"op": "show", "path": str(target), "line": a.line, "focus": a.focus})
    if not answer.get("shown"):
        raise _NoEditor(f"the editor didn't open {a.path}")


def _notify(a: argparse.Namespace) -> None:
    servers = registry.live()
    if not servers:
        raise _NoEditor("no editor server is running")
    _ask(servers, {"op": "message", "text": a.message})


def _ask(servers: list[registry.Record], message: dict[str, ty.Any]) -> dict[str, ty.Any]:
    """Ask the server in the caller's tmux session, else the newest, passing over any that
    doesn't answer."""
    unreachable = []
    for server in registry.by_preference(servers, registry.tmux_session()):
        try:
            answer = registry.request(server, message)
        except registry.Unreachable as error:
            unreachable.append(str(error))
            continue
        if "error" in answer:
            raise _NoEditor(answer["error"])
        return answer
    raise _NoEditor("; ".join(unreachable))


def _run_editor(a: argparse.Namespace) -> ty.NoReturn:
    try:
        a.editor_func(a)
    except _NoEditor as error:
        print(f"lemonaid editor: {error}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    lsp = subparsers.add_parser(
        "lsp", help="the review-comments language server, which an editor starts over stdio"
    )
    lsp.set_defaults(func=_lsp)

    editor = subparsers.add_parser(
        "editor",
        help="open a file or show a message in the editor running `lemonaid lsp`",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = editor.add_subparsers(dest="editor_command", required=True)

    opening = sub.add_parser(
        "open", help="open a file in the editor whose workspace holds it, in your tmux session"
    )
    opening.add_argument("path", type=pathlib.Path)
    opening.add_argument("--line", type=int, help="the line to show, from 1")
    opening.add_argument(
        "--focus", action="store_true", help="move the cursor there; by default it stays put"
    )
    opening.set_defaults(editor_func=_open)

    notify = sub.add_parser("notify", help="show a message in the editor")
    notify.add_argument("message")
    notify.set_defaults(editor_func=_notify)

    editor.set_defaults(func=_run_editor)
