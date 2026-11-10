"""`restore/` asks the front end about a lemon's terminal and never reads a terminal's
own metadata keys, so another front end can restore lemons without changing it."""

import ast
from pathlib import Path

_RESTORE = Path(__file__).parent.parent.parent / "src" / "lemonaid" / "restore"
_PREFIXES = ("tmux_", "wezterm_", "cmux_")


def _reads_front_end_keys(path: Path) -> bool:
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(_PREFIXES)
        for node in ast.walk(ast.parse(path.read_text()))
    )


def test_restore_reads_no_front_end_keys() -> None:
    assert {path.name for path in _RESTORE.glob("*.py") if _reads_front_end_keys(path)} == set()
