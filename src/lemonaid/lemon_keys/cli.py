"""`lemonaid key|keys`: the lemons the keys in the inbox and the grove reach, for a lemon told
"clean up 5e". Both show the same keys: each inbox row's is its lemon's grove key.
"""

__lazy_modules__ = ["lemonaid.grove.source", "lemonaid.places.ownership"]

import argparse
import json
import sys
import typing as ty
from collections import abc
from pathlib import Path

from ..brief import attached, identity
from ..config import load_config
from ..grove.source import live
from ..inbox import db
from ..lemon_watchers.common import detect_terminal_switch_source
from ..places import ownership
from . import lookup

_TERMINALS = ("tmux", "wezterm", "cmux")
_ANY = "any"  # every terminal's lemons, as a grove opened outside any of them shows


def _fail(args: argparse.Namespace, message: str) -> ty.NoReturn:
    if args.json:
        print(json.dumps({"error": message}))
    else:
        print(message, file=sys.stderr)
    raise SystemExit(1)


def _terminal(args: argparse.Namespace) -> str:
    """The terminal whose inbox shows the keys: the one given, else the one this runs in. An
    inbox lists only the lemons it can switch to, so its blocks and keys depend on it.
    """
    if args.terminal:
        return args.terminal

    detected = detect_terminal_switch_source()
    if detected == "unknown":
        _fail(
            args,
            "Can't tell which terminal's inbox the key comes from; pass --terminal "
            + "|".join((*_TERMINALS, _ANY)),
        )
    return detected


def _everything(terminal: str) -> list[lookup.Keyed]:
    grove = live.preview(load_config(), None if terminal == _ANY else terminal)
    return lookup.every(grove.blocks, grove.arrangement)


def _elsewhere(
    typed: str, terminal: str, found: abc.Sequence[lookup.Keyed]
) -> dict[str, list[lookup.Keyed]]:
    """What *typed* reaches in each other terminal's inbox, where that isn't *found*."""
    here = [k.lemon.channel for k in found]
    return {
        other: there
        for other in _TERMINALS
        if other != terminal
        and (there := lookup.resolve(_everything(other), typed))
        and [k.lemon.channel for k in there] != here
    }


def _details(found: abc.Sequence[lookup.Keyed]) -> list[dict[str, ty.Any]]:
    channels = [k.lemon.channel for k in found]
    with db.connect() as conn:
        lemon_ids, briefs = identity.by_channel(conn), attached.by_channel(conn, channels)
    places = ownership.managed_places(load_config())
    return [
        {
            "key": k.key,
            "tree_key": k.tree_key,
            "group": k.block.name,
            "tree": k.tree.label,
            "channel": k.lemon.channel,
            "name": k.lemon.name,
            "lemon_id": lemon_ids.get(k.lemon.channel, ""),
            "status": k.lemon.status,
            "place": place.key
            if k.lemon.cwd and (place := ownership.place_at(Path(k.lemon.cwd), places))
            else "",
            "directory": k.lemon.cwd,
            "session": k.lemon.session,
            "brief": str(briefs.get(k.lemon.channel, "")),
        }
        for k in found
    ]


def _line(lemon: dict[str, ty.Any]) -> str:
    fields = [lemon["lemon_id"] or "(no brief)", lemon["status"], f"place {lemon['place']}"]
    return f"{lemon['key'] or '-':6} {lemon['name']}  [{', '.join(f for f in fields if f)}]"


def _card(lemon: dict[str, ty.Any]) -> list[str]:
    rows = [
        ("Lemon-ID", lemon["lemon_id"]),
        ("status", lemon["status"]),
        ("place", lemon["place"]),
        ("directory", lemon["directory"]),
        ("session", lemon["session"]),
        ("brief", lemon["brief"]),
    ]
    return [_line(lemon), *(f"       {label:10} {value}" for label, value in rows if value)]


def _cmd_key(args: argparse.Namespace) -> None:
    terminal = _terminal(args)
    found = lookup.resolve(_everything(terminal), args.key)
    if not found:
        _fail(
            args,
            f"No lemon at grove key {args.key!r} in a {terminal} inbox;"
            f" `lemonaid keys --terminal {terminal}` lists them all",
        )

    lemons, elsewhere = _details(found), _elsewhere(args.key, terminal, found)
    if args.json:
        print(
            json.dumps(
                {
                    "key": args.key,
                    "terminal": terminal,
                    "lemons": lemons,
                    "elsewhere": {
                        other: [
                            {"key": k.key, "channel": k.lemon.channel, "name": k.lemon.name}
                            for k in there
                        ]
                        for other, there in elsewhere.items()
                    },
                }
            )
        )
        return

    head = found[0]
    print(
        f"{args.key} in a {terminal} inbox: {head.block.name or 'no group'}"
        + (f" / {head.tree.label}" if all(k.tree is head.tree for k in found) else "")
    )
    print("\n".join(line for lemon in lemons for line in _card(lemon)))
    for other, there in elsewhere.items():
        print(
            f"In a {other} inbox, {args.key} is {', '.join(k.lemon.name for k in there)}:"
            " ask which inbox the person means."
        )


def _cmd_keys(args: argparse.Namespace) -> None:
    lemons = _details(_everything(_terminal(args)))
    if args.json:
        print(json.dumps({"lemons": lemons}))
        return

    print("\n".join(_line(lemon) for lemon in lemons))


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    key = subparsers.add_parser(
        "key",
        help="The lemons a key typed in the inbox or grove reaches, as 5e, 5.e2, or a block's digit",
    )
    key.add_argument("key", help="A key as the inbox and grove show it: 5e, 5.e2, or 5")
    every = subparsers.add_parser("keys", help="Every lemon's inbox and grove key, one per line")
    for parser in (key, every):
        parser.add_argument(
            "--terminal",
            choices=(*_TERMINALS, _ANY),
            help="Whose inbox's keys: the terminal it runs in (default: this one's)",
        )
        parser.add_argument("--json", action="store_true", help="Print the lemons as JSON")
    key.set_defaults(func=_cmd_key)
    every.set_defaults(func=_cmd_keys)
