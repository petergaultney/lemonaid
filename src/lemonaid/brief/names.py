"""The name half of a Lemon-ID: from suggested words, `[brief] name`, or a random WordyBin.

lemonaid only needs a name to be short, unlikely to repeat, and safe in a Lemon-ID
and in the shell commands briefs hand to lemons. A name is also how a lemon signs,
so a new one never matches a name an active lemon holds (see `active_names`).
`[brief] name` is a shell command printing one, for someone who wants their lemons
named another way; the first word it prints is the name.
"""

import os
import random
import re
import subprocess
from collections import abc

import wordybin

from ..config import load_config
from . import name_words

_TIMEOUT_SECONDS = 5
_ATTEMPTS = 20
# No dot, which splits a Lemon-ID's slug from its name, and nothing a shell quotes.
_NAME = re.compile(r"[\w-]+")
_SLUG = re.compile(r"[a-z0-9-]+")


def _command() -> str:
    return load_config().brief.name.strip()


def _checked(name: str, source: str) -> str:
    if not _NAME.fullmatch(name):
        raise ValueError(f"{source} gave {name!r}; a name is letters, digits, _ and - only")

    capitalized = name[:1].upper() + name[1:]
    if _SLUG.fullmatch(capitalized):
        raise ValueError(f"{source} gave {name!r}; a name needs a capital letter or _")

    return capitalized


def _from_command(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"[brief] name {command!r} failed to run: {e}") from None

    name = next(iter(result.stdout.split()), "")
    if result.returncode != 0 or not name:
        raise ValueError(f"[brief] name {command!r} printed no name: {result.stderr.strip()}")

    return _checked(name, f"[brief] name {command!r}")


def new(held: abc.Container[str], words: name_words.Words = name_words.NONE) -> str:
    """A name not in *held* (lowercased names): the best one *words* make, else a fresh one.

    Raises ValueError when `[brief] name` fails, prints a bad name, or keeps printing
    held ones.
    """
    for name in name_words.names(words, random.Random()):
        if name.lower() not in held:
            return name

    command = _command()
    for _ in range(_ATTEMPTS):
        name = _from_command(command) if command else wordybin.encode(os.urandom(2))
        if name.lower() not in held:
            return name

    source = f"[brief] name {command!r}" if command else "WordyBin"
    raise ValueError(f"No free name from {source} after {_ATTEMPTS} tries")


def chosen(name: str) -> str:
    """*name*, picked by hand, as a Lemon-ID spells it; raises ValueError if it can't be one.

    With `[brief] name` unset it must be a five-letter word then a three-letter word,
    in any case. With it set, lemonaid can't tell what the command would print, so any
    safe name is taken as written.
    """
    if _command():
        return _checked(name, "--set")

    if shaped := name_words.shaped(name):
        return shaped

    raise ValueError(f"{name!r} is not a five-letter word and a three-letter word, like AuditInk")


def split_id(brief_id: str) -> tuple[str, str]:
    """A Brief-ID's name and description; the name is "" for an older ID without one.

    New IDs put the name first (`SkullHen.mc-tars`), older ones last
    (`mc-tars.SkullHen`). A description is a lowercase slug and a name never
    is, which tells the two orders apart.
    """
    name, dot, description = brief_id.partition(".")
    if dot and _SLUG.fullmatch(description) and not _SLUG.fullmatch(name):
        return name, description

    description, dot, name = brief_id.rpartition(".")
    return (name, description) if dot else ("", brief_id)


def join_id(name: str, description: str) -> str:
    return f"{name}.{description}"
