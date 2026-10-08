"""Persistent matching context beside a brief, without changing its saved commands."""

import json
import os
import pathlib
import tempfile

Context = dict[str, str]
Contexts = dict[str, list[Context]]


def load(path: pathlib.Path) -> Contexts:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return {}

    if not isinstance(value, dict) or any(
        not isinstance(command, str)
        or not isinstance(items, list)
        or not items
        or any(
            not isinstance(item, dict)
            or set(item) != {"cwd", "repo"}
            or any(not isinstance(v, str) for v in item.values())
            for item in items
        )
        for command, items in value.items()
    ):
        raise ValueError(f"Invalid waiter context in {path}")

    return value


def save(path: pathlib.Path, contexts: Contexts) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(contexts, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)
