import pytest

from lemonaid import go

from .shared import run
from .shared_tmux import _query, _record


def test_jump_selects_target_pane(server, clients):
    _query(server, "new-session", "-d", "-s", "target")
    _query(server, "split-window", "-d", "-t", "target")
    found = _record(server, "target:0.1")
    clients("source")
    run("codex:real")
    assert (
        _query(server, "list-clients", "-F", "#{pane_id}")
        == found.metadata["tmux_pane_identity"][0]
    )


def test_replacement_pane_is_rejected(server):
    _query(server, "split-window", "-d", "-t", "source")
    found = _record(server, "source:0.1")
    old_pane = found.metadata["tmux_pane_identity"][0]
    _query(server, "kill-pane", "-t", old_pane)
    _query(server, "split-window", "-d", "-t", "source")
    replacement = _query(server, "display-message", "-p", "-t", "source:0.1", "#{pane_id}")
    assert replacement != old_pane
    with pytest.raises(LookupError, match="gone or ambiguous"):
        go._pane(server, found)


def test_duplicate_window_links_resolve_one_pane(server):
    found = _record(server, "source:0")
    _query(server, "link-window", "-s", "source:0", "-t", "source:1")
    assert go._pane(server, found) == found.metadata["tmux_pane_identity"][0]


def test_shared_source_window_requires_explicit_client(server, clients):
    source_pane = _query(server, "display-message", "-p", "-t", "source", "#{pane_id}")
    _query(server, "new-session", "-d", "-s", "second")
    _query(server, "link-window", "-s", "source:0", "-t", "second:1")
    clients("source")
    clients("second")
    _query(server, "select-window", "-t", "second:1")
    with pytest.raises(LookupError, match="Use --client"):
        go._client(server, "", source_pane)
    explicit = _query(server, "list-clients", "-F", "#{client_name}").splitlines()[0]
    assert go._client(server, explicit, source_pane) == explicit
