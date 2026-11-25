"""What a resumed Claude lemon is given for the docs mode it has now."""

import pytest

from lemonaid.config import load_config
from lemonaid.docs import launch, mode
from lemonaid.hooks import session_brief


@pytest.fixture(autouse=True)
def _no_brief(monkeypatch):
    monkeypatch.setattr(session_brief, "attached", lambda data, harness: None)


@pytest.mark.usefixtures("root")
def test_a_lemon_changed_to_classic_resumes_without_its_packages(tmp_path):
    mode.record("claude", "abc", "packages")
    assert "--settings" in launch.resumed("abc", tmp_path, load_config(), "claude").claude_flags

    mode.record("claude", "abc", "classic")
    resumed = launch.resumed("abc", tmp_path, load_config(), "claude")

    assert resumed == launch.Launch({mode.ENV: "classic"})


@pytest.mark.usefixtures("root")
def test_a_lemon_changed_to_packages_resumes_with_them_built_now(tmp_path):
    mode.record("claude", "abc", "packages")

    resumed = launch.resumed("abc", tmp_path, load_config(), "claude")

    assert resumed.environment[mode.ENV] == "packages"
    assert "Write plainly." in (tmp_path / resumed.claude_flags[1]).read_text()
