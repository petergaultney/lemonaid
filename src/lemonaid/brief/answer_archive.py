"""Answer sidecars, saved before live entries are removed."""

import json
from pathlib import Path

from . import store


def path_for(brief: Path) -> Path:
    return brief.with_suffix(".answers.json")


def read(brief: Path) -> list[str]:
    path = path_for(brief)
    if not path.exists():
        return []

    entries = json.loads(path.read_text())
    if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
        raise ValueError(f"Invalid answer archive: {path}")

    return entries


def save(brief: Path, entries: list[str]) -> None:
    path = path_for(brief)
    if error := store.outside_error(path):
        raise ValueError(error)

    try:
        with path.open("x") as stream:
            stream.write("[]\n")
    except FileExistsError:
        pass

    def prepend(before: str) -> str:
        archived = json.loads(before)
        if not isinstance(archived, list) or not all(isinstance(entry, str) for entry in archived):
            raise ValueError(f"Invalid answer archive: {path}")
        # An interrupted removal can leave an entry both live and archived.
        return (
            json.dumps(list(dict.fromkeys([*entries, *archived])), ensure_ascii=False, indent=2)
            + "\n"
        )

    store.edit(path, prepend, migrate=False)
