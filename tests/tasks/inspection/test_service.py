import os
import threading

from lemonaid.tasks.inspection import inspector, passes, service


def _config(tmp_path, interval: float) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"[tasks]\nenabled = true\ninspect_interval = {interval}\n")
    os.utime(path, ns=(path.stat().st_mtime_ns + 1_000_000_000,) * 2)


def test_a_pass_runs_once_per_interval_and_none_when_it_is_off(tmp_path, monkeypatch):
    ran = []

    def run(config, ask, send, remembered=None):
        ran.append(send)
        return passes.Done(inspector.Pass(0, [], []), [], [])

    monkeypatch.setattr(passes, "run", run)
    state, quitting = service._State(), threading.Event()

    _config(tmp_path, 0)
    service.tick(state, quitting)
    off = (state.worker, state.checker)
    _config(tmp_path, 3600)
    service.tick(state, quitting)
    state.worker.join(5)
    service.tick(state, quitting)
    state.worker.join(5)
    on = list(ran)
    _config(tmp_path, 0)
    service.tick(state, quitting)

    assert off == (None, None) and on == [True] and state.checker is None
