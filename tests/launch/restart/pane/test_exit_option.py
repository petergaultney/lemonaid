import pytest

from lemonaid.launch.restart import pane


@pytest.mark.parametrize("local", ["", "off", "failed", "on"])
def test_inheritance_restored_exactly(server, local):
    if local:
        pane.run(server.socket, "set-option", "-p", "-t", server.pane, "remain-on-exit", local)
    before = pane.exit_option(server)
    assert before == local
    pane.preserve(server)
    assert pane.exit_option(server) == "on"
    pane.restore(server, before)
    assert pane.exit_option(server) == local
