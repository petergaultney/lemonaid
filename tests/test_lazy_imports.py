"""Fresh interpreters keep collection-time UI imports out of startup checks."""

import sys

import pytest

from tests.cli_startup_shared import run

_STARTUP = """
import sys
import lemonaid.cli

def check_imports():
    eager = sys.version_info < (3, 15)
    assert ('textual' in sys.modules) == eager
    assert ('lemonaid.inbox.tui.app' in sys.modules) == eager

check_imports()
sys.argv = ['lemonaid', '--help']
try:
    lemonaid.cli.main()
except SystemExit as error:
    assert error.code == 0
check_imports()
sys.argv = ['lemonaid', 'inbox', 'list', '--json']
lemonaid.cli.main()
check_imports()
"""


def test_tui_loads_and_mounts_after_cli_startup(tmp_path):
    run(
        tmp_path,
        _STARTUP
        + """
import asyncio
from lemonaid.inbox.tui import LemonaidApp
from lemonaid.lemon_watchers import watcher

async def check():
    app = LemonaidApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one('#inbox_list').is_mounted
    thread = watcher._watcher_thread
    assert thread is None or not thread.is_alive()

asyncio.run(check())
""",
    )


@pytest.mark.parametrize(
    "first_use",
    [
        """
from lemonaid.groups import color, store
assert color.parsed('teal') == '#008080'
try:
    color.parsed('not-a-color')
except store.GroupError:
    pass
else:
    raise AssertionError('invalid color accepted')
""",
        """
from lemonaid.brief import cli
assert cli.brief_popup.BriefPopup.__name__ == 'BriefPopup'
""",
        """
sys.argv = ['lemonaid', 'inbox', 'arrange', 'snapshot']
lemonaid.cli.main()
""",
        """
sys.argv = ['lemonaid', 'lemon', 'doctor', '--stalls', '--json']
lemonaid.cli.main()
""",
    ],
    ids=["color", "popup", "arranger", "stalls"],
)
def test_rendering_dependencies_load_on_first_use(tmp_path, first_use):
    run(tmp_path, _STARTUP + first_use + "\nassert 'textual' in sys.modules\n")


@pytest.mark.skipif(sys.version_info < (3, 15), reason="PEP 810 requires Python 3.15")
def test_deferred_import_error_reaches_caller(tmp_path):
    run(
        tmp_path,
        """
import importlib.abc
import sys

class MissingTextual(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'textual' or fullname.startswith('textual.'):
            raise ModuleNotFoundError('textual unavailable', name=fullname)

sys.meta_path.insert(0, MissingTextual())
import lemonaid.cli
from lemonaid.groups import color
try:
    color.parsed('teal')
except ModuleNotFoundError as error:
    assert error.name == 'textual'
else:
    raise AssertionError('deferred import failure was swallowed')
""",
    )
