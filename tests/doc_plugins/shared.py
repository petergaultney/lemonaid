import sys
from pathlib import Path

from lemonaid.doc_plugins import plugin
from lemonaid.plugins import command

_SCRIPT = Path(__file__).with_name("fake_plugin.py")


def fake(*flags: str, name: str = "fake") -> plugin.Plugin:
    """The plugin in fake_plugin.py, whose comments are lines `%% <author>: <text>`."""
    return command.Plugin(name, (sys.executable, "-I", str(_SCRIPT), *flags))


RELAY = plugin.defaults()[0]
