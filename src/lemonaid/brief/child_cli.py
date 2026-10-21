"""`brief new --child`: write a brief for a lemon that hasn't started, attached to no one.

The new lemon joins its parent's groups. The parent passes the printed path as `--brief` to `place open` or `lemon start`.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

from .. import groups, home
from ..config import load_config
from ..inbox import db
from ..watch import children_waiter
from . import child, created, identity, lemon, name_words_cli, store


def _parent(target: str) -> tuple[str, str]:
    """(Lemon-ID, tmux session) of the lemon *target* names, `self` being the caller."""
    with db.connect() as conn:
        if target == "self":
            channel = lemon.self_channel(conn)
            found = db.get_by_channel(conn, channel, unread_only=False)
            tmux_session = found.metadata.get("tmux_session") if found else ""
            return lemon.own_id(conn, channel), tmux_session or ""

        found = lemon.lemon_id(conn, target)
        try:
            return found, lemon.attachment(conn, target).tmux_session
        except LookupError:
            return found, ""


def _create(args: argparse.Namespace, today: datetime.date) -> tuple[Path, str, str]:
    """(path, Lemon-ID, parent Lemon-ID) of the new brief."""
    output_doc = args.output_doc or args.review_doc
    body = child.template(child.PACKAGED_DIR, child.user_dir(), args.template)
    vaults = load_config().brief.vaults
    values = {
        **(child.pr_values(args.pr, args.repo) if args.pr else {}),
        **(child.output_doc_values(output_doc, vaults) if output_doc else {}),
        **({"author": args.author} if args.author else {}),
    }
    try:
        parent = _parent(args.parent)
    except (LookupError, ValueError, store.ChangedUnderneath) as cause:
        raise child.Problem(f"--parent {args.parent}: {cause}") from None

    with db.connect() as conn:
        stamp = created.now(created.by(conn))
        words = (
            name_words_cli.given(args)
            if args.name_words
            else name_words_cli.of_parent(conn, parent[0])
        )
    title = args.title.strip()
    name = store.slug(args.slug or title)
    try:
        planned = store.new_lemon_id(
            store.briefs_dir() / f"{today.isoformat()}-{name}.md", words=words
        )
    except ValueError as e:
        raise child.Problem(str(e)) from None
    area = args.area.strip()
    text = child.render(
        body, title, planned, parent, today, values, area, values.get("output_doc", ""), stamp
    )  # fails before any file
    try:
        path = store.create_named(name, today, lambda _: text)
    except FileExistsError as e:
        raise child.Problem(f"{e.filename} already exists") from None

    try:
        with db.connect() as conn:
            lemon_id = identity.ensure(conn, path, regenerate_on_collision=True, words=words)
        if lemon_id != planned:
            store.edit(
                path,
                lambda _: child.render(
                    body,
                    title,
                    lemon_id,
                    parent,
                    today,
                    values,
                    area,
                    values.get("output_doc", ""),
                    stamp,
                ),
            )
        with db.connect() as conn:
            groups.sync.join_parents(conn, lemon_id, parent[0])
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    name_words_cli.report(words, lemon_id)
    return path, lemon_id, parent[0]


def given(args: argparse.Namespace) -> list[str]:
    """The --child options *args* sets, which mean nothing without --child."""
    defaults = {"template": "child", "parent": "self"}
    return [
        f"--{name.replace('_', '-')}"
        for name in (
            "template",
            "slug",
            "parent",
            "area",
            "pr",
            "repo",
            "output_doc",
            "review_doc",
            "author",
        )
        if getattr(args, name) != defaults.get(name, "")
    ]


def cmd(args: argparse.Namespace) -> None:
    try:
        if paused := home.layout.paused():
            raise child.Problem(paused)

        if args.review_doc:
            print("--review-doc is deprecated; use --output-doc", file=sys.stderr)

        path, lemon_id, parent_id = _create(args, datetime.date.today())
    except (child.Problem, ValueError, store.ChangedUnderneath) as problem:
        if args.json:
            print(json.dumps({"error": str(problem)}, ensure_ascii=False))
        else:
            print(problem, file=sys.stderr)
        sys.exit(1)

    if args.json:
        result = {"path": str(path), "lemon_id": lemon_id, "parent": parent_id, "error": None}
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(path)

    print(children_waiter.reminder(), file=sys.stderr)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("--child", "a brief for a lemon not started yet")
    group.add_argument(
        "--child",
        action="store_true",
        help="Write an unattached brief for --brief on `place open` or `lemon start`",
    )
    group.add_argument(
        "--template",
        default="child",
        help="A template in <lemons dir>/brief-templates/ or packaged (child, review)",
    )
    group.add_argument("--slug", default="", help="The filename's slug, instead of the title's")
    group.add_argument(
        "--parent",
        default="self",
        metavar="LEMON",
        help="Its parent: self (the default), a Lemon-ID, channel, or brief",
    )
    group.add_argument(
        "--area",
        default="",
        help="The part of the project the work is in (apps/unified-asset), shown after the project",
    )
    group.add_argument("--pr", default="", help="A PR URL, or a number with --repo ($pr_*)")
    group.add_argument("--repo", default="", help="owner/name, for a --pr number")
    group.add_argument(
        "--output-doc",
        default="",
        help="The document the work produces: recorded as `Output-Doc:` ($output_doc*)",
    )
    group.add_argument("--review-doc", default="", help=argparse.SUPPRESS)
    group.add_argument(
        "--author",
        default="",
        metavar="LEMON",
        help="The PR's author, if not the parent; $tell names it too",
    )
