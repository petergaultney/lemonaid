"""The signature a lemon's own doc waiter counts as answered, so a tool that writes its
replies signs with exactly that name: `lemonaid watch doc --signature DOC`."""

import argparse
import pathlib
from collections import abc

from ..brief import command, identity
from ..config import load_config
from . import subscriptions


def for_doc(
    brief_text: str, doc: pathlib.Path, cwd: pathlib.Path, vaults: abc.Collection[pathlib.Path]
) -> str:
    """The `--me` of the brief's `watch doc` line for *doc*, else `<brief name> (Author)`, as
    a Docs row is watched; "" when the brief has no Brief-ID to sign with."""
    for spec in subscriptions.read(brief_text, cwd, vaults=tuple(vaults)):
        if spec.kind == "doc" and pathlib.Path(spec.target[0]).resolve() == doc.resolve():
            return spec.me

    try:
        name = identity.brief_name(identity.read(brief_text))
    except ValueError:
        return ""

    return f"{name} (Author)" if name else ""


def run(doc: pathlib.Path) -> int:
    brief, error = command.own_brief(argparse.Namespace(session=None, channel=None, id=None))
    if brief is None:
        print(f"no signature: {error}")
        return 2

    found = for_doc(brief.read_text(), doc, pathlib.Path.cwd(), load_config().brief.vaults)
    if not found:
        print(f"no signature: the brief {brief} has no Brief-ID")
        return 2

    print(found)
    return 0
