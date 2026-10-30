"""The label client keeps each server's clients and panes for readers that would run `tmux`."""

import shutil
import threading

import pytest

from lemonaid.tmux import label_client, navigation, pane_state
from lemonaid.watch import waiter_lock

from . import shared

pytestmark = pytest.mark.skipif(not shutil.which("tmux"), reason="needs tmux")


def _row(fields: tuple[str, ...], **values: str) -> str:
    return "\t".join(values.get(field.lstrip("@"), "") for field in fields)


def test_a_listing_is_read_only_while_its_keeper_holds_the_lock():
    socket = "/tmp/no-such-server.sock"
    pane = _row(
        pane_state.PANE_FIELDS,
        pane_id="%3",
        window_id="@1",
        pane_active="1",
        window_active="1",
        session_attached="1",
        pane_tty="/dev/ttys003",
        session_name="work\twith a tab",
    )
    pane_state.publish(socket, [], [pane])

    assert pane_state.read(socket) is None

    held = waiter_lock.acquire(pane_state.lock_path(socket))
    assert held is not None
    with held:
        state = pane_state.read(socket)

        assert state is not None and state.panes[0]["session_name"] == "work\twith a tab"
        assert pane_state.receives_keys(state, "%3") is True
        assert pane_state.receives_keys(state, "%4") is None


def test_focus_counts_the_pane_behind_a_focused_scratch_inbox():
    clients = [
        _row(pane_state.CLIENT_FIELDS, window_id="@1", lemonaid_scratch="1", pane_tty="/dev/s")
    ]
    panes = [
        _row(pane_state.PANE_FIELDS, window_id="@1", pane_last="1", pane_tty="/dev/lemon"),
        _row(pane_state.PANE_FIELDS, window_id="@2", pane_last="1", pane_tty="/dev/other"),
    ]
    state = pane_state.State(
        pane_state._rows(pane_state.CLIENT_FIELDS, clients),
        pane_state._rows(pane_state.PANE_FIELDS, panes),
    )

    assert pane_state.focused_ttys(state) == {"/dev/s", "/dev/lemon"}


def test_the_label_client_keeps_panes_current_until_it_stops():
    with shared.server() as (socket, tmux):
        stop = threading.Event()
        client = threading.Thread(target=label_client.run, args=(socket, stop))
        client.start()
        try:
            shared.until(lambda: pane_state.read(socket) is not None)
            tmux("split-window", "-t", "work", "sleep", "600")
            tty = tmux("display-message", "-p", "-t", "work:0.1", "#{pane_tty}")

            shared.until(lambda: tty in (navigation.locations_by_tty(socket) or {}))

            assert navigation.locations_by_tty(socket)[tty].session == "work"
        finally:
            stop.set()
            client.join(10)

        assert pane_state.read(socket) is None
