"""The arranger process is sent changed snapshots, and its failures fall back and restart."""

import sys
import time

import pytest

from lemonaid.inbox.arrange import child

# Answers each snapshot with how many it has seen and the snapshot's `n`.
_COUNTER = """
import json, sys
for seen, line in enumerate(sys.stdin, 1):
    print(json.dumps({"seen": seen, "n": json.loads(line)["n"]}), flush=True)
"""


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


@pytest.fixture
def arrangers():
    started: list[child.Arranger] = []
    yield lambda *a, **kw: started.append(child.Arranger(*a, **kw)) or started[-1]
    for a in started:
        a.close()


def _until(arranger: child.Arranger, snapshot: dict, done, deadline: float = 5.0):
    """Ask, as the tick does, until *done* holds of the answer."""
    stop = time.monotonic() + deadline
    while time.monotonic() < stop:
        reply = arranger.answer(snapshot, 0.0)
        if done(reply):
            return reply

        time.sleep(0.01)
    raise AssertionError(f"no such answer; error={arranger.error!r}")


def test_a_snapshot_is_sent_only_when_it_changes(arrangers):
    a = arrangers(_python(_COUNTER), budget=1.0)

    assert _until(a, {"n": 1}, bool) == {"seen": 1, "n": 1}
    assert a.answer({"n": 1}, 0.0) == {"seen": 1, "n": 1}
    assert _until(a, {"n": 2}, lambda r: r["n"] == 2) == {"seen": 2, "n": 2}
    assert a.error == ""


def test_an_unchanged_snapshot_is_resent_after_a_while(arrangers):
    now = [0.0]
    a = arrangers(_python(_COUNTER), budget=1.0, resend=60.0, clock=lambda: now[0])
    _until(a, {"n": 1}, bool)

    now[0] = 61.0

    assert _until(a, {"n": 1}, lambda r: r["seen"] == 2)["seen"] == 2


def test_an_answer_that_isnt_json_falls_back(arrangers):
    a = arrangers(_python("import sys\nfor _ in sys.stdin: print('oops', flush=True)"), budget=1.0)

    assert a.answer({"n": 1}, 0.0) is None
    assert a.error == "answer isn't JSON (Expecting value): oops"


def test_an_exit_is_reported_with_its_last_words(arrangers):
    a = arrangers(_python("import sys\nsys.stdin.readline()\nsys.exit('no brief field')"))

    _until(a, {"n": 1}, lambda _: a.error.startswith("exited"))

    assert a.error == "exited 1: no brief field"


def test_a_silent_arranger_times_out(arrangers):
    a = arrangers(_python("import time\ntime.sleep(60)"), budget=0.0, timeout=0.2)

    _until(a, {"n": 1}, lambda _: bool(a.error))

    assert a.error == "no answer in 0.2s"


def test_a_command_that_wont_start_is_reported(arrangers):
    a = arrangers(["/nonexistent/arranger"])

    assert a.answer({"n": 1}, 0.0) is None
    assert a.error.startswith("can't start:")


def test_a_failed_arranger_restarts_after_a_backoff(arrangers, tmp_path):
    now = [0.0]
    script = tmp_path / "arranger.py"
    a = arrangers([sys.executable, str(script)], budget=1.0, clock=lambda: now[0])
    _until(a, {"n": 1}, lambda _: a.error.startswith("exited 2"))

    script.write_text(_COUNTER)  # fixed while lma waits out the backoff
    now[0] = 0.5
    assert a.answer({"n": 1}, 0.0) is None

    now[0] = 1.0

    assert _until(a, {"n": 1}, bool) == {"seen": 1, "n": 1}
    assert a.error == ""


def test_the_command_is_split_like_a_shell_with_home_expanded(monkeypatch):
    monkeypatch.setenv("HOME", "/home/sam")

    assert child.parse_command("lemonaid inbox arrange serve '~/my arranger.py'") == [
        "lemonaid",
        "inbox",
        "arrange",
        "serve",
        "/home/sam/my arranger.py",
    ]


def test_a_stalled_reader_never_blocks_the_tick(arrangers):
    """A snapshot bigger than the pipe holds, to a child that never reads, still times out."""
    a = arrangers(_python("import time\ntime.sleep(60)"), budget=0.05, timeout=0.2)
    snapshot = {"n": 1, "pad": "x" * 200_000}

    started = time.monotonic()
    a.answer(snapshot, 0.0)
    first = time.monotonic() - started
    _until(a, {**snapshot, "n": 2}, lambda _: bool(a.error))

    assert first < 0.15
    assert a.error == "no answer in 0.2s"


def test_a_slow_reader_is_sent_the_newest_snapshot(arrangers):
    a = arrangers(_python("import time\ntime.sleep(0.3)\n" + _COUNTER), budget=0.0, timeout=5.0)
    for n in range(1, 6):
        a.answer({"n": n}, 0.0)

    assert _until(a, {"n": 5}, bool)["n"] in (1, 5)
    assert _until(a, {"n": 5}, lambda r: r["n"] == 5)["seen"] <= 2
