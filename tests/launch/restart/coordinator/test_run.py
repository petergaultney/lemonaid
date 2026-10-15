import pytest

from lemonaid.inbox import db
from lemonaid.launch.restart import coordinator, state

from .. import shared


@pytest.mark.parametrize(
    "phase", ["quiescing", "stopping", "source-exited", "starting", "verifying"]
)
def test_interrupted_boundary_never_replays_signal_or_launch(tmp_path, monkeypatch, phase):
    monkeypatch.setattr(coordinator.process, "same", lambda source: False)
    monkeypatch.setattr(
        coordinator.process, "terminate", lambda *args: pytest.fail("repeated SIGTERM")
    )
    monkeypatch.setattr(coordinator.pane, "replace", lambda *args: pytest.fail("repeated launch"))
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        state.update(conn, token, phase)
    coordinator.run(token)
    with db.connect() as conn:
        operation = state.get(conn, token)
    assert operation["phase"] == "partial"
    assert not state.blocked(shared.CHANNEL)


def test_stop_timeout_restores_source_delivery_without_respawning(tmp_path, monkeypatch):
    monkeypatch.setattr(coordinator, "_recheck", lambda *args: None)
    monkeypatch.setattr(coordinator.pane, "preserve", lambda *args: None)
    monkeypatch.setattr(coordinator.pane, "restore", lambda *args: None)
    monkeypatch.setattr(coordinator.process, "same", lambda source: True)

    def timeout(*args):
        raise TimeoutError("still running")

    monkeypatch.setattr(coordinator.process, "terminate", timeout)
    monkeypatch.setattr(
        coordinator.startup, "run", lambda *args: pytest.fail("launched despite timeout")
    )
    restored = []
    monkeypatch.setattr(coordinator.watchers, "restore", lambda *args: restored.append(args))
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
    coordinator.run(token)
    assert restored
    with db.connect() as conn:
        assert state.get(conn, token)["phase"] == "failed"
    assert not state.blocked(shared.CHANNEL)


def test_abort_records_failure_to_restore_source_delivery(tmp_path, monkeypatch):
    monkeypatch.setattr(coordinator.process, "same", lambda source: True)
    monkeypatch.setattr(coordinator.pane, "restore", lambda *args: None)

    def deaf(*args):
        raise TimeoutError("Source watcher did not register; rearm delivery manually")

    monkeypatch.setattr(coordinator.watchers, "restore", deaf)
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        state.update(conn, token, "quiescing")
        coordinator.reconcile(conn, state.get(conn, token), "SIGTERM timeout")
        operation = state.get(conn, token)
    assert operation["phase"] == "failed"
    assert "SIGTERM timeout" in operation["error"]
    assert "rearm delivery manually" in operation["error"]


def test_legacy_incomplete_plan_fails_before_quiescing_without_starting_watchers(
    tmp_path, monkeypatch
):
    plan = {**shared.plan(tmp_path), "settings": {"environment": {"PATH": "/old"}}}
    monkeypatch.setattr(coordinator.process, "same", lambda source: True)
    monkeypatch.setattr(
        coordinator.pane, "restore", lambda *args: pytest.fail("changed an unquiesced pane")
    )
    monkeypatch.setattr(
        coordinator.watchers, "restore", lambda *args: pytest.fail("started a legacy watcher")
    )
    monkeypatch.setattr(
        coordinator.stopping, "stop", lambda *args: pytest.fail("quiesced before validation")
    )
    with db.connect() as conn:
        token = state.reserve(conn, plan)
    coordinator.run(token)
    with db.connect() as conn:
        operation = state.get(conn, token)
    assert operation["phase"] == "failed"
    assert "fresh native hook" in operation["error"]
