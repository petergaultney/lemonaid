import pytest

from lemonaid.codex import daemon_setup


def _home(tmp_path, config: str | None):
    home = tmp_path / ".codex"
    home.mkdir()
    if config is not None:
        (home / "config.toml").write_text(config)

    return home


@pytest.mark.parametrize(
    "config",
    [None, 'model = "x"\n', "[features]\nhooks = true\n", "[features]\ndaemon_auto_start = true\n"],
    ids=["no file", "no features", "key unset", "true"],
)
def test_warns_unless_daemon_auto_start_is_false(tmp_path, config):
    assert daemon_setup.daemon_auto_start_warning(_home(tmp_path, config))


def test_silent_when_false(tmp_path):
    assert not daemon_setup.daemon_auto_start_warning(
        _home(tmp_path, "[features]\ndaemon_auto_start = false\n")
    )


def test_silent_when_codex_is_not_installed(tmp_path):
    assert not daemon_setup.daemon_auto_start_warning(tmp_path / ".codex")
