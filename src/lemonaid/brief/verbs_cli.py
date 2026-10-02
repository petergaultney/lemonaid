"""`brief now`, `status`, `bullet`, `pr`, `waiter`: the edits a worker makes to its own brief.

The edits go through lemonaid rather than the file so a sandboxed lemon (Codex
writes only inside its workspace) can keep its own brief current. Each one is
checked: an edit whose result `brief check` fails is refused, whether or not
the brief failed before it, and the error lists the problems.
"""

import argparse
import sys
from collections import abc
from pathlib import Path

from ..config import load_config
from ..inbox import db
from . import check, command, layout, links, now_edit, pr, pr_table, store, waiters


def _edit(path: Path, change: abc.Callable[[str], str]) -> str:
    """An error, or "" once *change* is written; a result `brief check` fails is not."""

    def checked(before: str) -> str:
        after = change(before)
        with db.connect() as conn:
            problems = check.problems(conn, path, after)
        if problems:
            raise ValueError(
                f"Refused: {path.name} would fail `lemonaid brief check`: " + "; ".join(problems)
            )

        return after

    try:
        store.edit(path.resolve(), checked)
    except (store.ChangedUnderneath, ValueError) as e:
        return str(e)

    return ""


def _edited(args: argparse.Namespace, change: abc.Callable[[str], str]) -> None:
    path, error = command.own_brief(args)
    if path:
        error = _edit(path, change)
    command.finish(args, {"path": str(path) if path else None}, error, str(path))


def _cmd_now(args: argparse.Namespace) -> None:
    text = sys.stdin.read() if args.markdown == "-" else args.markdown
    _edited(args, lambda brief: now_edit.with_now(brief, layout.parse(text)))


def _cmd_status(args: argparse.Namespace) -> None:
    _edited(args, lambda brief: store.with_status(brief, args.state))


def _cmd_bullet(args: argparse.Namespace) -> None:
    vaults = load_config().brief.vaults
    if args.verb == "add":
        _edited(
            args,
            lambda brief: now_edit.add(brief, args.heading, links.linkify(args.text, vaults)),
        )
    elif args.verb == "set":
        _edited(
            args,
            lambda brief: now_edit.replace(brief, args.lead, links.linkify(args.text, vaults)),
        )
    else:
        _edited(args, lambda brief: now_edit.remove(brief, args.lead))


def _review(review: str, vaults: abc.Collection[Path]) -> tuple[str, str]:
    """(the Review cell, error) for a URL or a vault document's path."""
    if "://" in review:
        return f"[review doc]({review})", ""

    url = links.vault_link(Path(review), vaults)
    if url is None:
        return "", f"{review} is not a .md file under a `[brief] vaults` root"

    return f"[review doc]({url})", ""


def _cmd_pr(args: argparse.Namespace) -> None:
    if args.verb == "rm":
        _edited(
            args,
            lambda brief: now_edit.with_section(
                brief, "PRs", lambda body: pr_table.without(body, args.ref)
            ),
        )
        return

    config = load_config().brief
    url, error = pr.url_for(args.ref, config.pr_url)
    review, review_error = _review(args.review, config.vaults) if args.review else ("", "")
    if error or review_error:
        command.finish(args, {"path": None}, error or review_error)
        return

    _edited(
        args,
        lambda brief: now_edit.with_section(
            brief,
            "PRs",
            lambda body: pr_table.with_row(body, url, args.work, review if args.review else None),
        ),
    )


def _cmd_waiter(args: argparse.Namespace) -> None:
    if args.verb == "add":
        _edited(args, lambda brief: waiters.add(brief, args.command))
    elif args.verb == "set":
        _edited(args, lambda brief: waiters.replace(brief, args.match, args.command, args.head))
    else:
        _edited(args, lambda brief: waiters.remove(brief, args.match))


def _verbs(
    parent: argparse.ArgumentParser, dest: str
) -> abc.Callable[[str, str], argparse.ArgumentParser]:
    verbs = parent.add_subparsers(dest=dest, required=True)
    return lambda name, summary: command.parser(verbs, name, summary)


def add_parsers(brief_subparsers: argparse._SubParsersAction) -> None:
    now = command.parser(brief_subparsers, "now", "Replace the `## Now` section of a lemon's brief")
    now.add_argument("markdown", help="The new section body; - reads it from stdin")
    now.set_defaults(func=_cmd_now)

    status = command.parser(brief_subparsers, "status", "Set the Status line of a lemon's brief")
    status.add_argument("state", choices=store.STATES)
    status.set_defaults(func=_cmd_status)

    bullet = brief_subparsers.add_parser(
        "bullet",
        help="Add, replace, or remove one bullet in a lemon's `## Now`",
        description="Each edit keeps the sub-headings in order (Needs, Running, Waiting on, "
        "Next, PRs, Done), removes one left empty, and refuses a result `brief check` "
        "would fail.",
    )
    verb = _verbs(bullet, "verb")
    add = verb("add", "Add a bullet under a sub-heading; Done adds at the top")
    add.add_argument("heading", help="Needs <who>, Running, Waiting on, Next, or Done")
    add.add_argument("text")
    replace = verb("set", "Replace the one bullet whose text starts with LEAD")
    replace.add_argument("lead")
    replace.add_argument("text")
    remove = verb("rm", "Remove the one bullet whose text starts with LEAD")
    remove.add_argument("lead")
    bullet.set_defaults(func=_cmd_bullet)

    prs = brief_subparsers.add_parser(
        "pr", help="Add or remove a row of the `### PRs` table in a lemon's `## Now`"
    )
    verb = _verbs(prs, "verb")
    add = verb("add", "Add or update the row for a PR")
    add.add_argument("ref", help="The PR's URL, or its number when `[brief] pr_url` is set")
    add.add_argument("work", help="A few words on what the PR does")
    add.add_argument("--review", default="", help="The review doc: a URL, or a path in a vault")
    remove = verb("rm", "Remove the row for a PR")
    remove.add_argument("ref", help="The PR's URL, or its number when only one row has it")
    prs.set_defaults(func=_cmd_pr)

    waiter = brief_subparsers.add_parser(
        "waiter",
        help="Add, replace, or remove one waiter's command in a lemon's `## Waiters`",
        description="A missing `## Waiters` is added as the last section. SET and RM name a "
        "waiter by part of its command, case ignored, and refuse unless exactly one matches.",
    )
    verb = _verbs(waiter, "verb")
    add = verb("add", "List a waiter's command; listing it again changes nothing")
    add.add_argument("command")
    replace = verb("set", "Replace the one waiter whose command contains MATCH")
    replace.add_argument("match")
    replace.add_argument("command", nargs="?", default="", help="The new command")
    replace.add_argument("--head", default="", help="Keep the command, with this `--head`")
    remove = verb("rm", "Remove the one waiter whose command contains MATCH")
    remove.add_argument("match")
    waiter.set_defaults(func=_cmd_waiter)
