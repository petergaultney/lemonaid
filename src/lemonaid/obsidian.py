"""Obsidian vault roots: how a path under one is written, and the URL that opens it.

Obsidian names a vault after its folder, so a root's basename is its vault name.
"""

import urllib.parse
from collections import abc
from pathlib import Path


def spellings(root: Path) -> list[str]:
    """How text may write *root*: from `~` when it is under home, and in full."""
    home = Path.home()
    return [
        *([f"~/{root.relative_to(home).as_posix()}"] if root.is_relative_to(home) else []),
        root.as_posix(),
    ]


def url(vault: str, rest: str) -> str:
    """The `obsidian://` URL opening *rest*, a `.md` path relative to the root of *vault*."""
    query = urllib.parse.urlencode(
        {"vault": vault, "file": rest.removesuffix(".md")}, quote_via=urllib.parse.quote
    )
    return f"obsidian://open?{query}"


def vault_link(path: Path, vaults: abc.Collection[Path]) -> str | None:
    """The `obsidian://` URL of a `.md` file under one of the expanded vault roots, or None."""
    resolved = path.expanduser().resolve()
    roots = [root.expanduser().resolve() for root in vaults]
    root = next((root for root in roots if resolved.is_relative_to(root)), None)
    if root is None or resolved.suffix != ".md":
        return None

    return url(root.name, resolved.relative_to(root).as_posix())


def obsidian_url(path: Path, vaults: abc.Iterable[Path]) -> str:
    """The `obsidian://` URL opening *path*, or "" when it is under none of *vaults*."""
    for root in vaults:
        if path.is_relative_to(root):
            return url(root.name, path.relative_to(root).as_posix())

    return ""
