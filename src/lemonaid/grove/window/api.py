"""The page's calls into Python, as `window.pywebview.api.<name>`."""

import dataclasses
import webbrowser
from collections import abc
from typing import Any

from ...config import Config
from ...front_end import pick
from ...log import get_logger
from ..tui.frame import Grove
from . import data, edits, settings, usage

_log = get_logger("grove.window")


@dataclasses.dataclass
class Shared:
    """What the page's calls, the socket and the refresher share. Each field is replaced whole."""

    config: Config
    grove: Grove | None = None
    client: str = ""  # the tmux client tty the window was last summoned over
    terminal: Any = None  # the app that was frontmost then, which gets the focus back


class Api:
    """pywebview exposes an object's methods to the page; *hide* hides the window, and *refresh*
    starts a reload of the grove without waiting for it."""

    def __init__(
        self, shared: Shared, hide: abc.Callable[[], None], refresh: abc.Callable[[], None]
    ) -> None:
        self._shared, self._hide, self._refresh = shared, hide, refresh

    def data(self) -> dict | None:
        return data.shown(self._shared.grove) if self._shared.grove else None

    def jump(self, channel: str) -> str:
        problem = data.jump(channel, self._shared.client)
        if not problem:
            self._hide()
        return problem

    def dismiss(self) -> None:
        self._hide()

    def refusal(self, digit: str, key: str, x: int, y: int) -> str:
        grove = self._shared.grove
        return data.refusal(grove, digit, key, int(x), int(y)) if grove else "the grove is loading"

    def plant(self, digit: str, key: str, x: int, y: int) -> str:
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"

        problem = data.plant(grove, digit, key, int(x), int(y))
        if not problem:
            self._refresh()
        return problem

    def block_refusal(self, digit: str, sides: list[str], dx: int, dy: int) -> str:
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"
        return data.block_refusal(grove, digit, sides, int(dx), int(dy))

    def reframe(self, digit: str, sides: list[str], dx: int, dy: int) -> str:
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"

        problem = data.reframe(grove, digit, sides, int(dx), int(dy))
        if not problem:
            self._refresh()
        return problem

    def search(self, text: str) -> list[dict]:
        grove = self._shared.grove
        return data.search(grove, text) if grove else []

    def edit_info(self, action: str, digit: str, key: str, channel: str) -> dict:
        grove = self._shared.grove
        if grove is None:
            return {"problem": "the grove is loading"}
        return edits.info(grove, self._shared.config, action, digit, key, channel)

    def edit(self, action: str, digit: str, key: str, channel: str, answer: str) -> str:
        """Make an edit; what happened, for the page's message line. The grove is reloaded
        either way, since an edit can change some lemons and refuse others."""
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"

        here = pick.around_caller()  # the window runs in a tmux session of its own
        rename = here.rename_workspace if here else None
        done = edits.make(grove, self._shared.config, action, digit, key, channel, answer, rename)
        self._refresh()
        return done

    def open_link(self, url: str) -> None:
        """Open a PR's link in the browser; only web links, since the page draws what lemons wrote."""
        if url.startswith(("https://", "http://")):
            webbrowser.open(url)
        else:
            _log.warning("not opening %r", url)

    def look(self) -> dict:
        """What the config says about how the page looks."""
        tui = self._shared.config.tui
        return {
            "opacity": tui.grove_window_opacity,
            "flipKey": tui.grove_flip_key,
            "flipHold": tui.grove_flip == "hold",
            "usageKey": tui.keybindings.usage_view,
        }

    def usage(self) -> list[dict]:
        return usage.rows(self._shared.config)

    def stump_refusal(self, digit: str, key: str, dx: int, dy: int) -> str:
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"
        return data.stump_refusal(grove, digit, key, int(dx), int(dy))

    def stump_drop(self, digit: str, key: str, dx: int, dy: int) -> str:
        grove = self._shared.grove
        if grove is None:
            return "the grove is loading"

        problem = data.stump_drop(grove, digit, key, int(dx), int(dy))
        if not problem:
            self._refresh()
        return problem

    def settings(self) -> dict:
        return settings.load()

    def keep(self, kept: dict) -> None:
        settings.save(kept)

    def log(self, line: str) -> None:
        _log.info("page: %s", line)
