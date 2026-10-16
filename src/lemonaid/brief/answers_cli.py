"""Record chat answers and read or archive them."""

import argparse
import datetime
import sys

from . import answer_archive, answer_edit, answers, command, store, verbs_cli


def _answer(args: argparse.Namespace) -> None:
    answer = sys.stdin.read() if args.answer == "-" else args.answer
    when = datetime.datetime.now().astimezone()
    verbs_cli.edited(args, lambda text: answers.add(text, args.question, answer, when))


def _archive(args: argparse.Namespace) -> None:
    if args.all and args.count is not None:
        command.finish(args, {}, "Use COUNT or --all, not both")
        return

    path, error = command.own_brief(args)
    moved = 0
    if path:
        try:
            moved = answer_edit.archive(
                path, None if args.all else (args.count if args.count is not None else 1)
            )
        except (OSError, ValueError, store.ChangedUnderneath) as cause:
            error = str(cause)
    command.finish(
        args,
        {"path": str(path) if path else None, "archived": moved},
        error,
        f"Archived {moved} answers",
    )


def _expand(args: argparse.Namespace) -> None:
    path, error = command.own_brief(args)
    entries: list[str] = []
    if path:
        try:
            entries = answer_archive.read(path)
        except (OSError, ValueError) as cause:
            error = str(cause)
    body = "\n\n".join([f"## Archived answers ({len(entries)})", *entries])
    command.finish(args, {"path": str(path) if path else None, "answers": entries}, error, body)


def add_parsers(parsers: argparse._SubParsersAction) -> None:
    answer = command.parser(parsers, "answer", "Record a chat question and answer, newest first")
    answer.add_argument("question")
    answer.add_argument(
        "answer", nargs="?", default="-", help="Answer Markdown, or - for stdin (default)"
    )
    answer.set_defaults(func=_answer)

    parser = parsers.add_parser("answers", help="Archive live answers or expand the archive")
    verbs = parser.add_subparsers(dest="verb", required=True)
    archive = command.parser(verbs, "archive", "Archive answers from the top of Answers")
    archive.add_argument("count", nargs="?", type=int, help="How many to archive (default: 1)")
    archive.add_argument("--all", action="store_true", help="Archive every live answer")
    archive.set_defaults(func=_archive)
    expand = command.parser(
        verbs, "expand", "Print archived answers without restoring them to the brief"
    )
    expand.set_defaults(func=_expand)
