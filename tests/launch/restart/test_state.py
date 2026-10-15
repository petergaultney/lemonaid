import dataclasses
import threading
import time

import pytest

from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, native, process, state
from lemonaid.messages import codex_delivery, store

from . import shared


def test_reservation_drains_delivery_and_excludes_another_restart():
    entered, release = threading.Event(), threading.Event()

    def delivery():
        with state.admission(shared.CHANNEL) as allowed:
            assert allowed
            entered.set()
            assert release.wait(5)

    old = threading.Thread(target=delivery)
    old.start()
    assert entered.wait(5)
    tokens = []
    worker = threading.Thread(target=lambda: tokens.append(state.reserve(shared.plan())))
    worker.start()
    time.sleep(0.05)
    assert not tokens
    release.set()
    old.join(5)
    worker.join(5)
    assert tokens
    with pytest.raises(ValueError, match="already"):
        state.reserve(shared.plan())
    state.update(tokens[0], "started")
    with state.admission(shared.CHANNEL) as allowed:
        assert allowed


def test_pending_delivery_is_not_consumed_during_cutover(tmp_path):
    inbox = tmp_path / "inbox"
    pending = store.send(inbox, "keep me", "test")
    state.reserve(shared.plan())
    assert codex_delivery.deliver_next(inbox, shared.SESSION) is None
    assert pending.exists()


def test_expired_worker_becomes_partial_without_replaying_actions(monkeypatch):
    token = state.reserve(shared.plan())
    state.update(token, "starting")
    monkeypatch.setattr(state.time, "time", lambda: 10**12)
    assert state.get(token)["phase"] == "partial"
    monkeypatch.setattr(coordinator, "_execute", lambda *a: pytest.fail("destructive replay"))
    coordinator.run(token)
    assert native.recovery_required(shared.CHANNEL)


def test_fresh_hook_releases_manual_recovery_requirement(tmp_path, monkeypatch):
    token = state.reserve(shared.plan())
    state.update(token, "partial")
    source = dataclasses.replace(shared.SOURCE, pid=999)
    state.write(
        "native-" + state.key(shared.CHANNEL) + ".json", {"identity": dataclasses.asdict(source)}
    )

    with db.connect() as conn:
        shared.setup(conn, tmp_path)
    state.write(
        "native-" + state.key(shared.CHANNEL) + ".json", {"identity": dataclasses.asdict(source)}
    )
    monkeypatch.setattr(process, "same", lambda *a: True)
    assert not native.recovery_required(shared.CHANNEL)


def test_sigterm_timeout_keeps_source_watchers_and_does_not_respawn(monkeypatch):
    from lemonaid.launch.restart import pane, planning
    from lemonaid.watch import stopping

    plan = shared.plan()
    token = state.reserve(plan)
    monkeypatch.setattr(planning, "build", lambda *a: plan)
    monkeypatch.setattr(pane, "preserve", lambda *a: None)
    monkeypatch.setattr(pane, "restore", lambda *a: None)

    def timeout(*a):
        raise TimeoutError("still running")

    monkeypatch.setattr(process, "terminate", timeout)
    monkeypatch.setattr(process, "same", lambda *a: True)
    monkeypatch.setattr(stopping, "stop", lambda *a: pytest.fail("source watcher stopped"))
    monkeypatch.setattr(pane, "replace", lambda *a: pytest.fail("replacement started"))
    coordinator.run(token)
    assert state.get(token)["phase"] == "failed"
    assert not state.blocked(shared.CHANNEL)
