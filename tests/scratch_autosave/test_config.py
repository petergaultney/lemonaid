from lemonaid.config import load_config


def test_autosave_is_opt_in(monkeypatch, tmp_path):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("LEMONAID_CONFIG", str(path))
    assert not load_config().tmux_session.autosave_scratch_size
    path.write_text("[tmux-session]\nautosave_scratch_size = true\n")
    assert load_config().tmux_session.autosave_scratch_size
