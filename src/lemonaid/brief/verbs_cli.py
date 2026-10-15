"""`brief now`, `status`, `bullet`, `pr`, `waiter`: the edits a worker makes to its own brief.

The edits go through lemonaid rather than the file so a sandboxed lemon (Codex
writes only inside its workspace) can keep its own brief current. Each one is
checked: an edit whose result `brief check` fails is refused, except for
Questions headings already unmatched before the edit. The error lists the
problems. A brief that has already lost its `Parent:` line can still be edited,
but no edit may drop one.
"""

import argparse
import sys
from collections import abc
from pathlib import Path

from .. import obsidian
from ..config import load_config
from ..inbox import db
from . import (
    check,
    command,
    hidden,
    links,
    now_edit,
    pr,
    pr_table,
    status_guide,
    store,
    watching_cli,
)


def edit(path: Path, change: abc.Callable[[str], str], *, preserve_existing: bool = False) -> str:
    """An error, or "" once *change* is written."""

    def checked(before: str) -> str:
        after = change(before)
        existing_questions = set(
            check.structure(before) if preserve_existing else check.question_problems(before)
        )
        with db.connect() as conn:
            problems = [
                *(p for p in check.structure(after) if p not in existing_questions),
                *check.recorded(conn, path, after),
            ]
        if check.has_parent_line(before) and not check.has_parent_line(after):
            problems.append("the edit drops the `Parent:` line")
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


def edited(args: argparse.Namespace, change: abc.Callable[[str], str]) -> None:
    path, error = command.own_brief(args)
    if path:
        error = edit(path, change)
    command.finish(args, {"path": str(path) if path else None}, error, str(path))


def _cmd_now(args: argparse.Namespace) -> None:
    text = sys.stdin.read() if args.markdown == "-" else args.markdown
    edited(args, lambda brief: now_edit.replace_progress(brief, text, args.replace_all))


def _cmd_hide(args: argparse.Namespace) -> None:
    edited(args, lambda brief: hidden.with_hidden(brief, not args.show))


def _cmd_status(args: argparse.Namespace) -> None:
    if args.state in store.RETIRED:
        print(
            f"`{args.state}` is no longer set by hand; cleared Status, so the inbox shows"
            " whether the lemon is active, idle, deaf or dead",
            file=sys.stderr,
        )
    state = store.CLEAR if args.state in store.RETIRED else args.state
    edited(args, lambda brief: store.with_status(brief, state))


def _cmd_bullet(args: argparse.Namespace) -> None:
    vaults = load_config().brief.vaults
    if args.verb == "add":
        edited(
            args,
            lambda brief: now_edit.add(brief, args.heading, links.linkify(args.text, vaults)),
        )
    elif args.verb == "set":
        edited(
            args,
            lambda brief: now_edit.replace(brief, args.lead, links.linkify(args.text, vaults)),
        )
    else:
        edited(args, lambda brief: now_edit.remove(brief, args.lead))


def _review(review: str, vaults: abc.Collection[Path]) -> tuple[str, str]:
    """(the Review cell, error) for a URL or a vault document's path."""
    if "://" in review:
        return f"[review doc]({review})", ""

    url = obsidian.vault_link(Path(review), vaults)
    if url is None:
        return "", f"{review} is not a .md file under a `[brief] vaults` root"

    return f"[review doc]({url})", ""


def _cmd_pr(args: argparse.Namespace) -> None:
    if args.verb == "rm":
        edited(
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

    edited(
        args,
        lambda brief: now_edit.with_section(
            brief,
            "PRs",
            lambda body: pr_table.with_row(body, url, args.work, review if args.review else None),
        ),
    )


def _verbs(
    parent: argparse.ArgumentParser, dest: str
) -> abc.Callable[[str, str], argparse.ArgumentParser]:
    verbs = parent.add_subparsers(dest=dest, required=True)
    return lambda name, summary: command.parser(verbs, name, summary)


def add_parsers(brief_subparsers: argparse._SubParsersAction) -> None:
    watching_cli.add_parser(brief_subparsers)
    now = command.parser(
        brief_subparsers, "now", "Replace progress in `## Now`, keeping omitted PRs and Docs tables"
    )
    now.add_argument("markdown", help="The new section body; - reads it from stdin")
    now.add_argument(
        "--replace-all",
        action="store_true",
        help="Allow the new body to drop sub-headings the section has; "
        "`brief bullet add|set|rm` change one line",
    )
    now.set_defaults(func=_cmd_now)

    status = command.parser(
        brief_subparsers,
        "status",
        "Set the Status line of a lemon's brief; `clear` removes it, so the inbox shows the "
        "lemon's own state",
    )
    status.epilog = status_guide.GUIDE
    status.formatter_class = argparse.RawDescriptionHelpFormatter
    status.add_argument("state", choices=(*store.STATES, store.CLEAR, *store.RETIRED))
    status.set_defaults(func=_cmd_status)

    hide = command.parser(
        brief_subparsers,
        "hide",
        "Add `Hidden: yes` to a lemon's brief, so the inbox leaves it out of its default list",
    )
    hide.add_argument("--show", action="store_true", help="Remove the line instead")
    hide.set_defaults(func=_cmd_hide)

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
