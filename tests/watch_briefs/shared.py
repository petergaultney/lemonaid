import argparse

from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.watch import briefs_events, cli


def lemon(name, state="working", ask="", channel=""):
    path = store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {state}\n\n## Now\n\n### Needs Peter\n\n{ask}\n")
    with db.connect() as conn:
        if channel:
            db.add(conn, channel, "", name=name)
            attached.attach(conn, channel, path)
        lemon_id = identity.ensure(conn, path)
    return lemon_id, path


def link(child, parent):
    with db.connect() as conn:
        links.set_parent(conn, child, parent)


def open_watch(family, me="me", quiet=0, to=frozenset({"merge", "done"})):
    return briefs_events.open_watch(family[3], family[0], me, quiet, to)


def poll(w):
    sent = []
    briefs_events.poll(w, sent.append)
    return sent


def args(state_dir, *argv):
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser.add_subparsers())
    return parser.parse_args(
        ["watch", "briefs", "--children", *argv, "--state-dir", str(state_dir), "--quiet", "0"]
    )
