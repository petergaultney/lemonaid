"""lemonaid and the Slack plugin know each other only through the source protocol."""

import re
from pathlib import Path

_SRC = Path(__file__).parents[2] / "src"

# What core may still say about Slack: its default source entry, and examples in docstrings.
_ALLOWED = {
    "lemonaid/sources/plugin.py": '{"name": "slack", "command": "lemonaid-slack"}',
    "lemonaid/sources/__init__.py": "(a Slack thread,",
    "lemonaid/sources/problems.py": "(Slack signed out, say)",
    "lemonaid/sources/host.py": "a poll may page Slack",
    "lemonaid/watch/source_cli.py": "Slack thread (docs/source-plugins.md)",
    "lemonaid/inbox/tui/tables/layout.py": "a little slack",
}


def _python(package: str) -> list[Path]:
    return sorted((_SRC / package).rglob("*.py"))


def test_core_never_imports_the_slack_plugin():
    for path in _python("lemonaid"):
        assert "lemonaid_slack" not in path.read_text(), path


def test_the_slack_plugin_never_imports_lemonaid():
    for path in _python("lemonaid_slack"):
        assert not re.search(r"^\s*(from|import) lemonaid\b", path.read_text(), re.M), path


def test_core_code_says_slack_only_where_allowed():
    for path in _python("lemonaid"):
        name = str(path.relative_to(_SRC))
        for line in path.read_text().splitlines():
            if re.search(r"\b[Ss]lack\b", line) and _ALLOWED.get(name, "\0") not in line:
                raise AssertionError(f"{name}: {line.strip()}")
