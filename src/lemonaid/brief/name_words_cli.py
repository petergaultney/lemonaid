"""`--name-words`, and the parent's `Name words:` line it overrides."""

import argparse
import sqlite3
import sys

from . import identity, lemon, name_words


def add_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--name-words",
        default="",
        metavar="WORDS",
        help="Five- and three-letter words for the name, best first (audit,check,ink,web)",
    )


def given(args: argparse.Namespace) -> name_words.Words:
    """The `--name-words` in *args*; raises ValueError for a word that can't be used."""
    words = name_words.parse(args.name_words)
    if words.malformed:
        raise ValueError(f"--name-words: {', '.join(words.malformed)} is not five or three letters")

    return words


def of_parent(conn: sqlite3.Connection, parent_id: str) -> name_words.Words:
    """The words on *parent_id*'s `Name words:` line, any malformed ones dropped with a warning."""
    path = lemon.brief_of(conn, parent_id)
    try:
        words = name_words.read(path.read_text()) if path else None
    except OSError:
        words = None
    if words is None:
        return name_words.NONE

    if words.malformed:
        print(
            f"Skipping {', '.join(words.malformed)} on {parent_id}'s Name words line:"
            " not five or three letters",
            file=sys.stderr,
        )
    return name_words.Words(fives=words.fives, threes=words.threes)


def report(words: name_words.Words, lemon_id: str) -> None:
    """Say on stderr whether *lemon_id*'s name came from *words*."""
    if words == name_words.NONE:
        return

    name = identity.brief_name(lemon_id)
    five, three = name[:5].lower(), name[5:].lower()
    if (five in words.fives or not words.fives) and (three in words.threes or not words.threes):
        print(f"Named {name} from the name words", file=sys.stderr)
    else:
        print(f"Every name the name words make is taken; named {name} instead", file=sys.stderr)
