"""`lemonaid watch <source> <args>`: follow something a watch source's plugin reads, such as a
Slack thread (docs/source-plugins.md), and `lemonaid <source> ...`, the plugin's own commands.

Listed under a brief's `## Watching`, the lemon's unified watcher follows it. Run with an
attached brief, it records itself there; if the lemon's watcher runs, it exits there.
Otherwise it follows in the foreground, printing each batch (`--once`: the first, then exits),
until the lemon's watcher starts and takes over. It stops, exiting 1, at the first problem the
plugin reports, such as a sign-in it needs.
"""

import argparse
import os
import sys
import time
from collections import abc

from ..config import load_config
from ..sources import host, plugin
from . import (
    brief_record,
    cursors,
    delivery,
    push_scout,
    registry,
    source_events,
    wait_state,
)

_EVERY = 1.0  # seconds between looks in the foreground; a look asks nothing unless due


def _sources() -> tuple[plugin.Source, ...]:
    return load_config().watch.sources


def subscription(words: abc.Sequence[str]) -> tuple[plugin.Source, plugin.Words] | None:
    """The source and its words, when *words* (after `lemonaid watch`) name a source."""
    if not words or not (source := plugin.named(_sources(), words[0])):
        return None

    return source, plugin.words(words[1:])


def _handed_over(owner: str, source: str) -> str:
    return (
        f"{'push scout' if push_scout.running(owner) else 'watcher'} running; "
        f"it follows this {source} subscription from your brief's ## Watching, nothing to rearm"
    )


def _run(source: plugin.Source, a: argparse.Namespace) -> int:
    if a.args in (["-h"], ["--help"]):
        print(a.help_text)
        return 0

    given = plugin.words(a.args)
    try:
        target = host.check(source, given.args)
    except host.Failed as error:
        print(f"lemonaid watch {source.name}: {error}", file=sys.stderr)
        return 2

    a.me = given.me
    if error := brief_record.record(a, source.name):
        print(f"not started: could not record waiter: {error}")
        return 2

    owner = cursors.owner(a.me)
    if owner and wait_state.is_armed(owner):
        print(_handed_over(owner, source.name))
        return 0

    delivered: list[str] = []
    problems: list[str] = []

    def deliver(message: str) -> None:
        delivery.to_stdout(message)
        delivered.append(message)

    # apart from its watcher's cursors
    directory = cursors.directory(f"{source.name}-foreground", a.me)
    directory.mkdir(parents=True, exist_ok=True)
    poll = source_events.Poller(
        source, given.args, target, False, directory, owner, deliver, problems.append
    )
    try:
        with registry.watching(a, source.name, target):
            while not (given.once and delivered) and not poll.ended:
                poll()
                if problems:
                    print(f"stopped: {problems[0]}")
                    return 1

                time.sleep(_EVERY)
                if owner and wait_state.is_armed(owner):
                    print(_handed_over(owner, source.name))
                    return 0
    except KeyboardInterrupt:
        pass
    finally:
        poll.close()
    return 0


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    for source in _sources():
        ap = subparsers.add_parser(
            source.name,
            help=f"Follow what the {source.name} watch source reads",
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            usage=f"lemonaid watch {source.name} [--me NAME] [--once] ARGS...",
            add_help=False,
            prefix_chars="\0",  # every word goes to the plugin, but lemonaid's own options
        )
        ap.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="the plugin's arguments; --me NAME and --once are lemonaid's",
        )
        ap.set_defaults(
            func=lambda a, s=source: sys.exit(_run(s, a)), status=None, help_text=ap.format_help()
        )


def _exec(source: plugin.Source, args: abc.Sequence[str]) -> None:
    argv = [*source.plugin.argv, *(args or ["--help"])]
    try:
        os.execvpe(argv[0], argv, {**os.environ, **host.env(source)})
    except OSError as error:
        sys.exit(f"cannot run the {source.name} plugin ({argv[0]}): {error}")


def add_plugin_commands(subparsers: argparse._SubParsersAction) -> None:
    """`lemonaid <source> ...` for each source not named like one of lemonaid's own commands."""
    for source in _sources():
        if source.name in subparsers.choices:
            continue

        ap = subparsers.add_parser(
            source.name,
            help=f"The {source.name} watch source's own commands",
            add_help=False,
            prefix_chars="\0",  # so every word, `--help` too, goes to the plugin
        )
        ap.add_argument("args", nargs=argparse.REMAINDER)
        ap.set_defaults(func=lambda a, s=source: _exec(s, a.args))
