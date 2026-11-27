"""`[[skills.sources]]`: directories of skills to install besides lemonaid's packaged ones.

Each entry names its directory in one way: `path`; `command`, which prints the directory
(a plugin saying where its own skills are); or `fetch`, a command lemonaid runs with
`{dir}` set to a directory it keeps for the source, when that directory doesn't exist yet
(`git clone --depth 1 <url> {dir}`, say). `update`, with `fetch`, refreshes it. No shell
runs these, and lemonaid itself knows no version control.
"""

import dataclasses
import shlex
import sys


@dataclasses.dataclass(frozen=True)
class Source:
    name: str
    path: str = ""
    command: tuple[str, ...] = ()
    fetch: tuple[str, ...] = ()
    update: tuple[str, ...] = ()


def _entry(entry: object) -> Source | None:
    if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
        return None

    ways = [k for k in ("path", "command", "fetch") if isinstance(entry.get(k), str) and entry[k]]
    if len(ways) != 1 or (entry.get("update") and ways != ["fetch"]):
        return None

    split = {
        k: tuple(shlex.split(entry[k])) for k in ("command", "fetch", "update") if entry.get(k)
    }
    if not all(split.values()):
        return None

    if any(not any("{dir}" in arg for arg in split[k]) for k in ("fetch", "update") if k in split):
        return None

    return Source(entry["name"], path=entry.get("path", "") or "", **split)


def parse(data: object) -> tuple[Source, ...]:
    entries = data.get("sources", []) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        print("Warning: [skills] sources must be a list of tables", file=sys.stderr)
        return ()

    found: list[Source] = []
    for entry in entries:
        source = _entry(entry)
        if source is None:
            print(
                f"Warning: [[skills.sources]] {entry!r} needs a name and one of path, command or"
                " fetch (fetch and update use {dir}); ignored",
                file=sys.stderr,
            )
        elif source.name == "lemonaid" or any(s.name == source.name for s in found):
            print(f"Warning: [[skills.sources]] {source.name!r} is taken; ignored", file=sys.stderr)
        else:
            found.append(source)
    return tuple(found)
