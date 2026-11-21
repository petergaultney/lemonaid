"""`lemonaid grove`: the grove map from the command line, for people and lemons."""

__lazy_modules__ = ["lemonaid.grove.source", "lemonaid.grove.tui"]

import argparse
import json
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.segment import Segment, Segments

from ..config import load_config
from ..lemon_watchers.common import detect_terminal_switch_source
from . import as_json, edit_cli, garden_cli, graft_cli, layout_cli
from .draw import block_scene, canvas, scenes
from .layout import advice
from .source import live, standalone
from .tui.frame import Grove
from .window import cli as window_cli


def _grove(save: bool, where: Path | None) -> Grove:
    config = load_config()
    source = detect_terminal_switch_source()
    switch_source = None if source == "unknown" else source
    if save:
        return live.fresh(config, switch_source, where)
    return live.preview(config, switch_source, where)


def _cmd_show(args: argparse.Namespace) -> None:
    where = layout_cli.proposed(args, args.layout) if args.layout else None
    grove = _grove(not args.dry_run, where)
    found, arrangement = grove.blocks, grove.arrangement
    size = shutil.get_terminal_size((214, 64))
    screen = args.width or size.columns, args.height or size.lines - 1
    if args.json:
        advised = advice.advise(found, arrangement, screen)
        print(
            json.dumps(
                as_json.grove(found, arrangement)
                | {"warnings": [a._asdict() for a in advised], "screen": list(screen)}
            )
        )
        return

    picture = canvas.blank(*screen)
    chosen = next((block for block in found if block.digit == args.block), None)
    if args.block and chosen is None:
        print(
            f"No block {args.block}; blocks are {', '.join(b.digit for b in found)}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    astray: list[str] = []
    if chosen:
        block_scene.zoomed(picture, chosen, arrangement, phase=0.0, astray=astray)
    else:
        scenes.overview(picture, found, arrangement, phase=0.0)
    if astray and chosen:
        keys = (f"{chosen.digit}{arrangement.trees[(chosen.name, key)].letter}" for key in astray)
        print(
            f"Lists drawn away from their trees at {picture.width}x{picture.height}: "
            f"{', '.join(keys)}",
            file=sys.stderr,
        )
    if args.plain:
        print("\n".join(canvas.plain_lines(picture)))
        return

    console = Console(
        force_terminal=True, color_system="truecolor", width=picture.width, highlight=False
    )
    for row in picture.rows:
        console.print(Segments([*canvas.line_segments(row), Segment.line()]), end="")


def _cmd_open(_args: argparse.Namespace) -> None:
    source = detect_terminal_switch_source()
    standalone.run(load_config(), None if source == "unknown" else source)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "grove",
        help="The grove map (beta): groups as blocks, places as trees",
        description="Draw the grove the inbox's grove view shows, or print its layout as JSON. "
        "Beta: commands, JSON and layout files may change between releases. See docs/grove.md.",
    )
    grove_subparsers = parser.add_subparsers(dest="grove_command", required=True)
    show = grove_subparsers.add_parser("show", help="Draw the grove, or one block of it")
    show.add_argument("block", nargs="?", default="", help="A block's digit, to draw it zoomed in")
    show.add_argument(
        "--width", type=int, default=0, help="Columns to draw (default: the terminal's)"
    )
    show.add_argument(
        "--height", type=int, default=0, help="Rows to draw (default: the terminal's)"
    )
    show.add_argument("--plain", action="store_true", help="Characters only, without color")
    show.add_argument("--dry-run", action="store_true", help="Don't save new plots or spots")
    show.add_argument(
        "--json", action="store_true", help="Print the blocks, trees and lemons as JSON"
    )
    show.add_argument(
        "--layout",
        type=Path,
        metavar="FILE",
        help="Draw the proposed layout in FILE (from `grove propose`) instead of the live one",
    )
    show.set_defaults(func=_cmd_show)
    grove_subparsers.add_parser(
        "open", help="Open the grove full-screen here; choosing a lemon switches to it"
    ).set_defaults(func=_cmd_open)
    edit_cli.add_parsers(grove_subparsers)
    garden_cli.add_parsers(grove_subparsers)
    graft_cli.add_parsers(grove_subparsers)
    layout_cli.add_parsers(grove_subparsers)
    window_cli.add_parsers(grove_subparsers)
