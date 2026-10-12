"""Ratchet: code outside `lemonaid/tmux/` reaches tmux only from files listed in _ALLOWED.

Delete names from _ALLOWED as files stop importing `lemonaid.tmux` or spawning `tmux`;
a file may not be added.

The check sees imports of `tmux` and list literals that start with "tmux"; a tuple, a
shell string or `shutil.which("tmux")` is not detected, so a pass is not proof that
nothing outside `tmux/` spawns it.
"""

import ast
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src" / "lemonaid"

_ALLOWED: set[str] = {
    "brief/children_cli.py",
    "brief/dismiss.py",
    "brief/handoff_tmux.py",
    "brief/popup.py",
    "brief/session.py",
    "brief/sidebar.py",
    "claude/status_note.py",
    "cli.py",
    "daily_date.py",
    "go.py",
    "handlers.py",
    "inbox/doctor.py",
    "inbox/resume_archived.py",
    "inbox/self_session.py",
    "inbox/tui/app.py",
    "inbox/tui/focus.py",
    "inbox/tui/utils.py",
    "inbox/unarchive.py",
    "launch/command.py",
    "launch/window.py",
    "lemon_watchers/common.py",
    "lemon_watchers/watcher.py",
    "messages/autoresume_tmux.py",
    "places/escape.py",
    "places/inbox_cleanup.py",
    "places/lifecycle.py",
    "places/ownership.py",
    "places/plan.py",
    "places/session.py",
    "places/target.py",
    "places/teardown.py",
    "places/windows.py",
    "places/workspace.py",
    "restore/cli.py",
    "skills/install.py",
    "watch/briefs_orphans.py",
}


def _is_tmux_module(name: str) -> bool:
    parts = name.split(".")

    return parts[0] == "tmux" or parts[:2] == ["lemonaid", "tmux"]


def _couples_to_tmux(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_tmux_module(node.module):
            return True

        if (
            isinstance(node, ast.ImportFrom)
            and (node.module == "lemonaid" or (not node.module and node.level))
            and any(alias.name == "tmux" for alias in node.names)
        ):
            return True

        if isinstance(node, ast.Import) and any(_is_tmux_module(a.name) for a in node.names):
            return True

        if (
            isinstance(node, ast.List)
            and node.elts
            and isinstance(node.elts[0], ast.Constant)
            and node.elts[0].value == "tmux"
        ):
            return True

    return False


def _coupled_files() -> set[str]:
    return {
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if path.relative_to(_SRC).parts[0] != "tmux"
        and _couples_to_tmux(ast.parse(path.read_text()))
    }


def test_no_new_files_couple_to_tmux() -> None:
    assert _coupled_files() - _ALLOWED == set()


def test_allowlist_has_no_stale_entries() -> None:
    assert _ALLOWED - _coupled_files() == set()
