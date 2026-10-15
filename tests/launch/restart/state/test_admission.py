from lemonaid.inbox import db
from lemonaid.launch.restart import state

from .. import shared


def test_only_token_generation_can_register_but_cannot_deliver(tmp_path, monkeypatch):
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        state.update(conn, token, "verifying")
    assert state.blocked(shared.CHANNEL, replacement=True)
    monkeypatch.setenv("LEMONAID_RESTART_TOKEN", token)
    assert not state.blocked(shared.CHANNEL, replacement=True)
    assert state.blocked(shared.CHANNEL)
