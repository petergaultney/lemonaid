"""Edit the subscription commands in a brief."""

import argparse

from . import command, verbs_cli, waiters


def _cmd_waiter(args: argparse.Namespace) -> None:
    if args.verb == "add":
        verbs_cli.edited(args, lambda brief: waiters.add(brief, args.command))
    elif args.verb == "set":
        verbs_cli.edited(
            args, lambda brief: waiters.replace(brief, args.match, args.command, args.head)
        )
    else:
        verbs_cli.edited(args, lambda brief: waiters.remove(brief, args.match))


def add_parser(brief_subparsers: argparse._SubParsersAction) -> None:
    waiter = brief_subparsers.add_parser(
        "watching",
        aliases=["waiter"],
        help="Add, replace, or remove one waiter's command in a lemon's `## Watching`",
        description="A missing `## Watching` is added as the last section. SET and RM name a "
        "waiter by part of its command, case ignored, and refuse unless exactly one matches.",
    )
    sub = waiter.add_subparsers(dest="verb", required=True)

    def verb(name: str, summary: str) -> argparse.ArgumentParser:
        return command.parser(sub, name, summary)

    add = verb("add", "List a waiter's command; listing it again changes nothing")
    add.add_argument("command")
    replace = verb("set", "Replace the one waiter whose command contains MATCH")
    replace.add_argument("match")
    replace.add_argument("command", nargs="?", default="", help="The new command")
    replace.add_argument("--head", default="", help="Keep the command, with this `--head`")
    remove = verb("rm", "Remove the one waiter whose command contains MATCH")
    remove.add_argument("match")
    waiter.set_defaults(func=_cmd_waiter)
