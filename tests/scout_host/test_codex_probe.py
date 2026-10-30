"""The Codex setup probe is safe to run from many scout threads at once."""

import threading

from lemonaid.watch import delivery


def test_concurrent_probes_all_find_a_writable_codex_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setattr(delivery.shutil, "which", lambda name: "/usr/bin/codex")
    start = threading.Barrier(16)
    problems: list[str] = []

    def probe() -> None:
        start.wait()
        problems.extend(delivery.codex_setup_problem() for _ in range(50))

    threads = [threading.Thread(target=probe) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert problems == [""] * 800
    assert list(tmp_path.iterdir()) == []
