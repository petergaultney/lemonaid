"""Patching the Claude Code binary for faster notifications, from the inbox's `P` key."""

from pathlib import Path

from textual.app import App

from ...claude.patcher import apply_patch
from . import error_screen


def apply(app: App, binary: Path) -> str:
    """Patch *binary* and say how it went; its patch status afterwards."""
    try:
        count = apply_patch(binary)
    except Exception as e:  # a key handler's top level: any failure is shown, not raised
        error_screen.show(app, "Patch failed", str(e))
        return "unpatched"

    if count <= 0:
        error_screen.show(app, "Nothing to patch", "No patterns were found in the Claude binary.")
        return "unpatched"

    app.notify(f"Patched Claude Code ({count} locations). Restart Claude for effect.")
    return "patched"
