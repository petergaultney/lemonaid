"""Generic heading operations and explicit legacy layout migration."""

import argparse
import sys

from ..inbox import db
from . import attached, command, migrate, section_edit, sections, store, verbs_cli


def _section(args: argparse.Namespace) -> None:
    if args.verb == "show":
        path, error = command.own_brief(args)
        body = ""
        if path:
            try:
                heading = sections.find(path.read_text(), args.heading)
                if heading is None:
                    error = f"No heading {args.heading!r}"
                else:
                    body = "\n".join(sections.body(path.read_text(), heading))
            except ValueError as cause:
                error = str(cause)
        command.finish(args, {"body": body}, error, body)
        return
    body = (
        sys.stdin.read()
        if args.verb == "set" and args.markdown == "-"
        else getattr(args, "markdown", "")
    )
    verbs_cli.edited(
        args,
        lambda text: section_edit.change(
            text,
            args.heading,
            lambda _: body.splitlines(),
            level=getattr(args, "level", 2),
            parent=getattr(args, "parent", "Now"),
            keep_empty=args.verb == "set",
        ),
    )


def _migrate(args: argparse.Namespace) -> None:
    if not args.all:
        verbs_cli.edited(args, migrate.layout)
        return
    if args.use_self or args.session or args.channel or args.id is not None:
        command.finish(args, {}, "Use --all or a single target, not both")
        return
    with db.connect() as conn:
        paths = list(
            dict.fromkeys(
                a.path.resolve()
                for a in attached.everything(conn)
                if not (a.notification and a.notification.is_archived)
            )
        )
    errors = []
    for path in paths:
        error = store.outside_error(path)
        if not error:
            error = (
                verbs_cli.edit(path, migrate.layout, preserve_existing=True)
                if path.is_file()
                else f"No brief at {path}"
            )
        if error:
            errors.append(f"{path}: {error}")
    command.finish(
        args,
        {"paths": [str(p) for p in paths]},
        "\n".join(errors),
        f"Migrated {len(paths) - len(errors)} briefs",
    )


def add_parsers(parsers: argparse._SubParsersAction) -> None:
    parser = parsers.add_parser("section", help="Show, replace, or remove any heading by name")
    verbs = parser.add_subparsers(dest="verb", required=True)
    for name in ("show", "set", "rm"):
        verb = command.parser(verbs, name, f"{name.capitalize()} a heading and its body")
        verb.add_argument("heading")
        if name == "set":
            verb.add_argument(
                "markdown", nargs="?", default="-", help="Body, or - for stdin (default)"
            )
            verb.add_argument(
                "--level",
                type=int,
                choices=range(2, 7),
                default=2,
                help="Level when creating a heading",
            )
            verb.add_argument("--parent", default="Now", help="Parent when creating a subheading")
        verb.set_defaults(func=_section)
    parser = command.parser(
        parsers,
        "migrate",
        "Promote legacy Next, PRs, Docs and Done headings",
        target_required=False,
    )
    parser.add_argument(
        "--all", action="store_true", help="Migrate active attached and pending briefs"
    )
    parser.set_defaults(func=_migrate)
