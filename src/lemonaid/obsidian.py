"""Obsidian vault roots: how a path under one is written, and the URL that opens it.

Obsidian names a vault after its folder, so a root's basename is its vault name.
"""

import urllib.parse
import urllib.request
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


def _local_path(link: str) -> Path | None:
    try:
        parsed = urllib.parse.urlsplit(link)
    except ValueError:
        return None

    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return path if path.suffix == ".md" else None

    if parsed.scheme == "obsidian" and parsed.netloc == "open":
        path = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
        return Path(path) if path else None

    return None


def by_vault(link: str, vaults: abc.Collection[Path]) -> str:
    """*link* as an `obsidian://open?vault=` URL when it names a note under one of the expanded
    *vaults* by its path on this machine, and unchanged otherwise.

    A link by path opens only on the machine that wrote it; one by vault opens on any machine with
    a vault of that name.
    """
    path = _local_path(link)
    found = obsidian_url(path, vaults) if path is not None and path.is_absolute() else ""
    if not found:
        return link

    heading = urllib.parse.urlsplit(link).fragment
    return f"{found}#{heading}" if heading else found
