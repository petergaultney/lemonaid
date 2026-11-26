"""The pages `grove serve` sends, each with the scripts it needs run before its own.

The grove page is the window's canvas, made for a pointer and a keyboard. A phone is sent to the
list of groups in its place, which opens a lemon's page as the canvas does.
"""

import dataclasses
import json
from importlib import resources

from ... import web_config
from ..window import page

_ICONS = {"icon.svg": "image/svg+xml", "apple-touch-icon.png": "image/png"}
_LINKS = '<link rel="icon" href="icon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="apple-touch-icon.png">'


def _first(scripts: str, into: str) -> str:
    """*into* with *scripts* run before its own, and the grove's icon."""
    into = into.replace("</head>", f"{_LINKS}</head>", 1)
    at = into.index("<script")
    return f"{into[:at]}<script>\n{scripts}</script>\n{into[at:]}"


def _keys(keys: web_config.WebConfig) -> str:
    """The page's own scripts' first: its notes for the log, then its prefix key."""
    here = resources.files(__package__)
    return (
        f"{here.joinpath('notes.js').read_text()}\n"
        f"window.groveKeys = {json.dumps(dataclasses.asdict(keys))};\n"
        f"{here.joinpath('prefix.js').read_text()}"
    )


def grove(keys: web_config.WebConfig) -> str:
    """The window's page, with the shim that turns its Python calls into requests first."""
    shim = resources.files(__package__).joinpath("shim.js").read_text()
    return _first(f"{shim}\n{_keys(keys)}", page.html())


def lemon(keys: web_config.WebConfig) -> str:
    return _first(_keys(keys), resources.files(__package__).joinpath("lemon.html").read_text())


def groups(keys: web_config.WebConfig) -> str:
    return _first(_keys(keys), resources.files(__package__).joinpath("groups.html").read_text())


def served(keys: web_config.WebConfig) -> dict[str, tuple[bytes, str]]:
    """Each page and icon by its path, with its content type."""
    here, html = resources.files(__package__), "text/html; charset=utf-8"
    return {
        "grove": (grove(keys).encode(), html),
        "lemon": (lemon(keys).encode(), html),
        "groups": (groups(keys).encode(), html),
        **{name: (here.joinpath(name).read_bytes(), kind) for name, kind in _ICONS.items()},
    }


def for_phone(user_agent: str) -> bool:
    """Phones name themselves "Mobile" in their user agent, and tablets mostly don't: a tablet's
    screen fits the grove."""
    return "Mobile" in user_agent
