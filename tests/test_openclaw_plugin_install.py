"""Installing lemonaid's plugin into OpenClaw's gateway."""

import json
import subprocess

import pytest

from lemonaid.openclaw import plugin_install


def _installing() -> list[list[str]]:
    ran: list[list[str]] = []
    plugin_install.install("openclaw", run=ran.append)
    return ran


def test_a_first_install_links_the_copy_and_lets_it_read_turns():
    assert _installing() == [
        ["plugins", "install", "--link", "--force", str(plugin_install.root())],
        ["config", "set", "plugins.entries.lemonaid.hooks.allowConversationAccess", "true"],
        ["plugins", "reload", "lemonaid"],
    ]
    settings = json.loads((plugin_install.root() / "lemonaid.json").read_text())
    assert settings["version"] == plugin_install.version()
    assert (plugin_install.root() / "index.js").is_file()
    assert plugin_install.installed()


def test_installing_again_changes_nothing_unless_the_plugin_changed():
    _installing()

    assert _installing() == []

    (plugin_install.root() / "index.js").write_text("// an older plugin\n")

    assert _installing() == [["plugins", "reload", "lemonaid"]]


def test_the_copy_names_the_python_and_lemonaid_variables_where_it_was_installed(monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", "/srv/lemonaid.db")
    _installing()

    settings = json.loads((plugin_install.root() / "lemonaid.json").read_text())

    assert settings["env"]["LEMONAID_DB"] == "/srv/lemonaid.db"
    assert settings["python"]


def test_uninstalling_removes_it_from_openclaw_and_the_copy():
    _installing()
    ran: list[list[str]] = []

    plugin_install.uninstall("openclaw", run=ran.append)

    assert ran == [["plugins", "uninstall", "lemonaid", "--force"]]
    assert not plugin_install.root().exists()
    assert plugin_install.status().startswith("not installed")


def test_a_reload_that_failed_is_retried_and_turns_stay_with_the_observer_until_it_works():
    def failing(arguments: list[str]) -> None:
        if arguments[:2] == ["plugins", "reload"]:
            raise subprocess.CalledProcessError(1, arguments)

    with pytest.raises(subprocess.CalledProcessError):
        plugin_install.install("openclaw", run=failing)

    assert not plugin_install.installed()
    assert plugin_install.status().startswith("not loaded")
    assert _installing() == [["plugins", "reload", "lemonaid"]]
    assert plugin_install.installed()


def test_an_update_whose_reload_failed_is_retried():
    _installing()
    (plugin_install.root() / "index.js").write_text("// an older plugin\n")

    def failing(arguments: list[str]) -> None:
        raise subprocess.CalledProcessError(1, arguments)

    with pytest.raises(subprocess.CalledProcessError):
        plugin_install.install("openclaw", run=failing)

    assert _installing() == [["plugins", "reload", "lemonaid"]]
