from pathlib import Path

import pytest

from lemonaid.docs import mode, mode_cli


@pytest.fixture
def rooted(tmp_path):
    (tmp_path / "config.toml").write_text(f'[docs]\nroots = ["{tmp_path / "docs"}"]\n')


@pytest.mark.usefixtures("rooted")
def test_a_parent_changes_a_lemon_s_mode_by_a_prefix_of_its_session(capsys):
    mode.record("codex", "019a-thread", "packages")
    mode.record("claude", "abc-session", "packages")

    mode_cli.run(["codex:019a", "classic"], own=False)

    assert mode.wanted("codex", "019a-thread", "packages") == "classic"
    assert "at its next compaction or resume" in capsys.readouterr().out


@pytest.mark.usefixtures("rooted")
def test_a_lemon_changes_and_shows_its_own_mode(capsys, monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc-session")

    mode_cli.run(["packages"], own=True)
    mode_cli.run([], own=True)

    printed = capsys.readouterr().out.splitlines()
    assert "when it is next resumed through lemonaid" in printed[0]
    assert printed[1] == "claude abc-session: packages"


def test_without_roots_it_says_what_the_lemon_gets_meanwhile(capsys):
    mode.record("claude", "abc-session", "classic")

    mode_cli.run(["abc", "packages"], own=False)

    assert "Without [docs] roots it gets classic" in capsys.readouterr().out
    assert Path(mode.paths.session_mode("claude", "abc-session")).read_text() == "packages"


@pytest.mark.parametrize("words", [["nobody", "classic"], ["abc", "lean"]])
def test_an_unknown_session_or_mode_changes_nothing(words):
    mode.record("claude", "abc-session", "classic")

    with pytest.raises(SystemExit):
        mode_cli.run(words, own=False)

    assert mode.wanted("claude", "abc-session", "") == "classic"
