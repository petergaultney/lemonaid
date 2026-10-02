"""scripts/changelog-section.py picks out one version's notes for its GitHub Release."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "changelog-section.py"
_SPEC = importlib.util.spec_from_file_location("changelog_section", _SCRIPT)
changelog_section = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(changelog_section)

_CHANGES = """# 0.58.3 (2026-10-02)

#### Changed

- **Newest.**

# 0.58.2 (2026-10-02)

#### Fixed

- **Middle,** with a `# 0.1.0` lookalike inside.

## 0.4.10 (2026-01-26)

- Old-style heading.
"""


def _section(version: str) -> str | None:
    return changelog_section.section(_CHANGES.splitlines(keepends=True), version)


def test_section_runs_to_the_next_version_heading():
    assert _section("0.58.3") == "#### Changed\n\n- **Newest.**\n"
    assert _section("0.58.2") == "#### Fixed\n\n- **Middle,** with a `# 0.1.0` lookalike inside.\n"


def test_old_double_hash_heading_is_a_section_too():
    assert _section("0.4.10") == "- Old-style heading.\n"


def test_missing_or_prefix_version_has_no_section():
    assert _section("0.58.4") is None
    assert _section("0.58") is None


def test_real_changelog_has_the_current_version():
    root = _SCRIPT.parent.parent
    version = next(
        line.split('"')[1]
        for line in (root / "pyproject.toml").read_text().splitlines()
        if line.startswith("version = ")
    )
    with (root / "CHANGES.md").open() as f:
        assert changelog_section.section(f, version)
