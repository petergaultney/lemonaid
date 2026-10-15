import threading

import pytest

from lemonaid.inbox import db
from lemonaid.launch.restart import state

from .. import shared


def test_reservation_serializes_and_expiry_reconciles_without_restarting(tmp_path, monkeypatch):
    monkeypatch.setattr(state.expiry.process, "same", lambda source: False)
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        with pytest.raises(ValueError, match="in progress"):
            state.reserve(conn, shared.plan(tmp_path))
        conn.execute("UPDATE lemon_restarts SET deadline = 0 WHERE token = ?", (token,))
        conn.commit()
        assert not state.blocked(shared.CHANNEL)
        assert state.get(conn, token)["phase"] == "partial"
        assert state.recovery_required(conn, shared.CHANNEL)
        state.update(conn, token, "failed", error="inspect")
        assert not state.blocked(shared.CHANNEL)


def test_reservation_waits_for_inflight_delivery(tmp_path):
    inside, release, reserved = threading.Event(), threading.Event(), threading.Event()

    def deliver():
        with state.admission(shared.CHANNEL) as allowed:
            assert allowed
            inside.set()
            assert release.wait(3)

    def reserve():
        with db.connect() as conn:
            state.reserve(conn, shared.plan(tmp_path))
            reserved.set()

    with db.connect():
        pass
    sender = threading.Thread(target=deliver)
    worker = threading.Thread(target=reserve)
    sender.start()
    assert inside.wait(3)
    worker.start()
    try:
        assert not reserved.wait(0.1)
    finally:
        release.set()
        sender.join(3)
        worker.join(3)
    assert reserved.is_set()
