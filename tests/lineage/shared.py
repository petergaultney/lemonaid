import argparse
import contextlib
import json

from lemonaid import lineage, messages
from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db


def lemon(name: str, channel: str = "", status: str = "working") -> str:
    """A brief named *name*, attached to *channel* when one is given. Returns its Lemon-ID."""
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {status}\n")
    with db.connect() as conn:
        if channel:
            db.add(conn, channel, "", metadata={})
            attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def run(capsys, *argv: str) -> dict:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    lineage.cli.setup_parser(subparsers)
    messages.cli.add_tell_parser(subparsers)
    args = parser.parse_args(argv)
    with contextlib.suppress(SystemExit):
        args.func(args)

    out = capsys.readouterr()
    return json.loads(out.out) if "--json" in argv else {"out": out.out, "err": out.err}
