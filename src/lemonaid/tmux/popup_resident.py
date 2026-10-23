"""The resident behind a fast popup: the popup's app, running in its hidden session.

A popup app is a module with `run(opener, rename_session, hide)`, which runs for as long as the
session lives: *opener()* is the tmux client the popup was last opened over, *rename_session(old,
new)* renames a tmux session, saying why it couldn't or "", and *hide()* closes the popup,
leaving the app running for the next one.
"""

import functools
import importlib

from . import fast_popup, rename


def serve(name: str) -> None:
    importlib.import_module(fast_popup.module_for(name)).run(
        functools.partial(fast_popup.opener, name),
        rename.session,
        functools.partial(fast_popup.hide, name),
    )
