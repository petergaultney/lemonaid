import json

from lemonaid.claude import statusline

_PAYLOAD = {
    "workspace": {"current_dir": "/tmp/x"},
    "model": {"display_name": "Opus 5.5"},
    "session_name": "my session",
}


def _render(capsys, monkeypatch, tmp_path, config: str | None) -> str:
    path = tmp_path / "config.toml"
    if config is not None:
        path.write_text(config)
    monkeypatch.setenv("LEMONAID_CONFIG", str(path))
    statusline.render_statusline(json.loads(json.dumps(_PAYLOAD)))
    return capsys.readouterr().out


def test_default_is_not_faint(capsys, monkeypatch, tmp_path):
    out = _render(capsys, monkeypatch, tmp_path, None)

    assert "\033[2m" not in out
    assert " \033[38;2;216;135;96mOpus 5.5" in out
    assert " \033[38;5;248m(my session)" in out


def test_label_color_number(capsys, monkeypatch, tmp_path):
    out = _render(capsys, monkeypatch, tmp_path, "[claude.statusline]\nlabel_color = 111\n")

    assert " \033[38;5;111m(my session)" in out


def test_label_color_default_foreground(capsys, monkeypatch, tmp_path):
    out = _render(capsys, monkeypatch, tmp_path, '[claude.statusline]\nlabel_color = "default"\n')

    assert " (my session)\033[0m" in out


def test_label_color_dim_restores_faint(capsys, monkeypatch, tmp_path):
    out = _render(capsys, monkeypatch, tmp_path, '[claude.statusline]\nlabel_color = "dim"\n')

    assert " \033[2m(my session)" in out


def test_malformed_tables_fall_back_to_default(capsys, monkeypatch, tmp_path):
    out = _render(capsys, monkeypatch, tmp_path, 'claude = "oops"\n')

    assert " \033[38;5;248m(my session)" in out
