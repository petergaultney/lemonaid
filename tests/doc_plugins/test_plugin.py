import sys
from pathlib import Path

from lemonaid import watch_config
from lemonaid.doc_plugins import plugin
from lemonaid.plugins import command


def test_relay_comments_is_the_default_and_found_in_lemonaids_environment():
    [relay] = plugin.defaults()

    assert relay.name == "relay-comments"
    assert relay.argv == (str(Path(sys.executable).parent / "lemonaid-relay-comments"),)


def test_configured_plugins_replace_the_default_in_order():
    config = watch_config.parse(
        {
            "doc": {
                "plugins": [
                    {"name": "mine", "command": "/opt/bin/mine --strict"},
                    {"name": "relay-comments", "command": "lemonaid-relay-comments"},
                ]
            }
        }
    )

    assert [p.name for p in config.doc_plugins] == ["mine", "relay-comments"]
    assert config.doc_plugins[0].argv == ("/opt/bin/mine", "--strict")


def test_an_empty_list_turns_every_plugin_off():
    assert watch_config.parse({"doc": {"plugins": []}}).doc_plugins == ()


def test_an_entry_without_a_command_or_named_twice_is_skipped(capsys):
    found = plugin.parse(
        [{"name": "a", "command": "a"}, {"name": "b"}, {"name": "a", "command": "other"}]
    )

    assert found == (command.Plugin("a", ("a",)),)
    assert "needs a name and a command" in capsys.readouterr().err
