"""Where the scout host is started: detached, or in a systemd user unit of its own."""

from lemonaid.watch import scout_start
from lemonaid.watch.scout_start import _spawn  # conftest replaces the module's copy per test


def test_inside_a_systemd_unit_the_host_gets_its_own_unit(monkeypatch, tmp_path):
    runs, popens = [], []
    monkeypatch.setenv("INVOCATION_ID", "abc")
    monkeypatch.setenv("OPENCLAW_GATEWAY_PORT", "18789")
    monkeypatch.setattr(scout_start.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(scout_start.subprocess, "run", lambda argv, **kw: runs.append(argv))
    monkeypatch.setattr(scout_start.subprocess, "Popen", lambda argv, **kw: popens.append(argv))
    monkeypatch.setattr(scout_start.scout_roster, "log_path", lambda: tmp_path / "scout.log")

    _spawn()

    assert popens == []
    [argv] = runs
    assert argv[:3] == ["systemd-run", "--user", "--collect"]
    assert argv[-3:] == ["lemonaid", "watch", "host"]
    assert "--setenv=OPENCLAW_GATEWAY_PORT=18789" in argv
    assert not any(arg.startswith("--setenv=INVOCATION_ID=") for arg in argv)


def test_outside_systemd_the_host_is_a_detached_process(monkeypatch, tmp_path):
    popens = []
    monkeypatch.delenv("INVOCATION_ID", raising=False)

    def run(argv, **kw):
        raise AssertionError(f"ran {argv}")

    monkeypatch.setattr(scout_start.subprocess, "run", run)
    monkeypatch.setattr(scout_start.subprocess, "Popen", lambda argv, **kw: popens.append(kw))
    monkeypatch.setattr(scout_start.scout_roster, "log_path", lambda: tmp_path / "scout.log")

    _spawn()

    [kwargs] = popens
    assert kwargs["start_new_session"] is True
