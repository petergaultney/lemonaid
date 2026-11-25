"""The docs a Claude lemon is launched with, in its system prompt.

Claude cuts hook context over 10,000 characters to a preview, so the packages a lemon
starts with go in a file passed as `--append-system-prompt-file`. Beside it, a manifest
names each doc in that file and its modification time then. The launch hands the
manifest's path to the session in `START_ENV`; the session's first `SessionStart` claims
it, so a `claude -p` the lemon runs, which inherits the variable, can't.
"""

import json
import os
import uuid
from collections import abc
from dataclasses import dataclass
from pathlib import Path

from ..log import get_logger
from . import frontmatter, paths, sections

START_ENV = "LEMONAID_DOCS_START"

_log = get_logger("docs.start")


@dataclass(frozen=True)
class Member:
    package: str
    doc: frontmatter.Doc


def members(docs: abc.Sequence[frontmatter.Doc], names: abc.Iterable[str]) -> list[Member]:
    """The docs in the packages *names*, in package then index order, each doc once."""
    found: dict[Path, Member] = {}
    for name in names:
        for doc in docs:
            if name in doc.packages and doc.path not in found:
                found[doc.path] = Member(name, doc)
    return list(found.values())


def block(path: Path, text: str, section: str = "") -> str:
    """*text* from *path*, headed so the lemon knows where it came from."""
    where = f'{path}, section "{section}"' if section else str(path)
    return f"Contents of {where} (delivered by lemonaid):\n\n{text}"


def write(given: abc.Iterable[Member], settings: abc.Mapping | None) -> tuple[Path, list[str]]:
    """Write the start text for *given* and its manifest; the manifest's path and the
    Claude flags that load the text (and *settings*, when there are any).

    Raises OSError when a doc can't be read or the files can't be written.
    """
    folder = paths.state_dir() / "docs" / "starts"
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / uuid.uuid4().hex
    blocks, docs = [], {}
    for member in given:
        path = member.doc.path
        mtime = path.stat().st_mtime
        blocks.append(block(path, sections.text(path.read_text())))
        docs[f"{path}#"] = {"mtime": mtime, "package": member.package}
    text = stem.with_suffix(".md")
    text.write_text("\n\n".join(blocks) + "\n")
    flags = ["--append-system-prompt-file", str(text)]
    if settings:
        stem.with_suffix(".settings.json").write_text(json.dumps(settings))
        flags += ["--settings", str(stem.with_suffix(".settings.json"))]
    manifest = stem.with_suffix(".json")
    manifest.write_text(json.dumps({"docs": docs, "flags": flags, "session": ""}))
    return manifest, flags


def _read(manifest: Path) -> dict:
    try:
        loaded = json.loads(manifest.read_text())
    except (OSError, ValueError) as e:
        _log.warning("could not read the start manifest %s: %s", manifest, e)
        return {}

    return loaded if isinstance(loaded, dict) else {}


def claim(session: str, source: str) -> dict:
    """The manifest in `START_ENV`, claimed for *session*; {} without one, or when another
    session started from it first.

    A Claude `/clear` begins a new session in the same process, whose system prompt
    still holds the text, so a `clear`, `compact` or `resume` start can always claim it.
    """
    named = os.environ.get(START_ENV, "")
    manifest = Path(named) if named else None
    loaded = _read(manifest) if manifest else {}
    if not manifest or not loaded:
        return {}

    if loaded.get("session") not in ("", session) and source == "startup":
        return {}

    if not loaded.get("session"):
        try:
            manifest.write_text(json.dumps({**loaded, "session": session}))
        except OSError as e:
            _log.warning("could not claim %s for %s: %s", manifest, session, e)
    return loaded
