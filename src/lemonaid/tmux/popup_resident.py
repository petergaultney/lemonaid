"""The resident behind a fast popup: the popup's app, running in its hidden session.

A popup app is a module with `run(opener, rename_session, hide, take_zoom)`, which runs for as
long as the session lives: *opener()* is the tmux client the popup was last opened over,
*rename_session(old, new)* renames a tmux session, saying why it couldn't or "", *hide()* closes
the popup, leaving the app running for the next one, and *take_zoom()* is what the popup was last
opened to show, once (see `fast_popup.show`).
"""

import functools
import importlib

from . import fast_popup, rename


def serve(name: str) -> None:
    importlib.import_module(fast_popup.module_for(name)).run(
        functools.partial(fast_popup.opener, name),
        rename.session,
        functools.partial(fast_popup.hide, name),
        functools.partial(fast_popup.take_zoom, name),
    )
