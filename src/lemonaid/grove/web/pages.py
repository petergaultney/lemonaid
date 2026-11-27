"""The pages `grove serve` sends, each with the scripts it needs run before its own.

The grove page is the window's canvas, made for a pointer and a keyboard. A phone is sent to the
list of groups in its place, which opens a lemon's page as the canvas does.
"""

import dataclasses
import json
from importlib import resources

from ... import web_config
from ..window import page

_FILES = {
    "icon.svg": "image/svg+xml",
    "apple-touch-icon.png": "image/png",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-maskable.png": "image/png",  # Android's: fills the shape it crops an icon to
}
_MANIFEST = "manifest.webmanifest"  # what a phone installs the grove as
_LINKS = (
    '<link rel="icon" href="icon.svg" type="image/svg+xml">'
    '<link rel="apple-touch-icon" href="apple-touch-icon.png">'
    '<link rel="manifest" href="manifest.webmanifest"><meta name="theme-color" content="#0b0e13">'
)


def _first(scripts: str, into: str) -> str:
    """*into* with *scripts* run before its own, and the grove's icons and manifest."""
    into = into.replace("</head>", f"{_LINKS}</head>", 1)
    at = into.index("<script")
    return f"{into[:at]}<script>\n{scripts}</script>\n{into[at:]}"


def _keys(keys: web_config.WebConfig) -> str:
    """The page's own scripts' first: its notes for the log, this device's vault names, then its
    prefix key."""
    here = resources.files(__package__)
    return (
        f"{here.joinpath('notes.js').read_text()}\n"
        f"{here.joinpath('vaults.js').read_text()}\n"
        f"window.groveKeys = {json.dumps(dataclasses.asdict(keys))};\n"
        f"{here.joinpath('prefix.js').read_text()}"
    )


def grove(keys: web_config.WebConfig) -> str:
    """The window's page, with the shim that turns its Python calls into requests first."""
    shim = resources.files(__package__).joinpath("shim.js").read_text()
    return _first(f"{shim}\n{_keys(keys)}", page.html())


def _phone(keys: web_config.WebConfig, name: str, own: tuple[str, ...] = ()) -> str:
    """A page made for a phone, which edits a lemon in a sheet of its own (`edit.js`) and keeps
    conversations to draw at once (`talks.js`), and runs its *own* scripts before its body's."""
    here = resources.files(__package__)
    scripts = "\n".join(here.joinpath(each).read_text() for each in ("edit.js", "talks.js", *own))
    return _first(f"{_keys(keys)}\n{scripts}", here.joinpath(name).read_text())


def lemon(keys: web_config.WebConfig) -> str:
    return _phone(keys, "lemon.html", ("attach.js",))


def groups(keys: web_config.WebConfig) -> str:
    return _phone(keys, "groups.html")


def vaults(keys: web_config.WebConfig) -> str:
    return _phone(keys, "vaults.html")


def _manifest(app: str) -> bytes:
    shown = json.loads(resources.files(__package__).joinpath(_MANIFEST).read_text())
    return json.dumps({**shown, "name": app, "short_name": app}, indent=2).encode()


def served(keys: web_config.WebConfig, app: str) -> dict[str, tuple[bytes, str]]:
    """Each page, icon and the manifest by its path, with its content type. *app* names the grove
    installed as an app."""
    here, html = resources.files(__package__), "text/html; charset=utf-8"
    return {
        "grove": (grove(keys).encode(), html),
        "lemon": (lemon(keys).encode(), html),
        "groups": (groups(keys).encode(), html),
        "vaults": (vaults(keys).encode(), html),
        **{name: (here.joinpath(name).read_bytes(), kind) for name, kind in _FILES.items()},
        _MANIFEST: (_manifest(app), "application/manifest+json"),
    }


def for_phone(user_agent: str) -> bool:
    """Phones name themselves "Mobile" in their user agent, and tablets mostly don't: a tablet's
    screen fits the grove."""
    return "Mobile" in user_agent
