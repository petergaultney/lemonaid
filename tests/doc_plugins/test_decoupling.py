"""lemonaid and the Relay plugin know each other only through the plugin protocol."""

import re
from pathlib import Path

_SRC = Path(__file__).parents[2] / "src"

# What core may still say about Relay: its default plugin entry, and the old Docs label and
# template variable that briefs and user templates written before plugins still use.
_ALLOWED = {
    "lemonaid/doc_plugins/plugin.py": 'command": "lemonaid-relay-comments',
    "lemonaid/brief/doc_table.py": '_OLD_COMMENTS = "Relay comments"',
    "lemonaid/brief/child.py": '"relay_name":',
}


def _python(package: str) -> list[Path]:
    return sorted((_SRC / package).rglob("*.py"))


def test_core_never_imports_the_relay_plugin():
    for path in _python("lemonaid"):
        assert "lemonaid_relay_comments" not in path.read_text(), path


def test_the_relay_plugin_never_imports_lemonaid():
    for path in _python("lemonaid_relay_comments"):
        assert not re.search(r"^\s*(from|import) lemonaid\b", path.read_text(), re.M), path


def test_core_code_has_no_relay_markup_or_names():
    for path in _python("lemonaid"):
        name = str(path.relative_to(_SRC))
        for line in path.read_text().splitlines():
            if (
                re.search(r"\brelay\b|relay_|<<\}\}|(?<![#{])\{==", line, re.I)
                and _ALLOWED.get(name, "\0") not in line
            ):
                raise AssertionError(f"{name}: {line.strip()}")
