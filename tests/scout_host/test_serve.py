"""The host runs one scout per registration, replaces or retries it, and exits when idle.

The scouts here are fakes; nothing is delivered anywhere.
"""

import json
import threading
import time

import pytest

from lemonaid.watch import registry, scout_host, scout_roster


def _until(condition, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


class _Fake:
    """Records each scout started, and ends one with the outcome set for its lemon."""

    def __init__(self) -> None:
        self.started: list[scout_roster.Registration] = []
        self.outcomes: dict[str, str] = {}
        self.stopped: list[str] = []

    def __call__(self, registration, stopping):
        self.started.append(registration)
        while registration.lemon_id not in self.outcomes:
            if stopping():
                self.stopped.append(registration.token)
                return "stopped"

            time.sleep(0.01)
        outcome = self.outcomes.pop(registration.lemon_id)
        if outcome == "crash":
            raise RuntimeError("boom")

        return outcome


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(scout_host, "_TICK", 0.02)
    monkeypatch.setattr(scout_host, "RETRY_SECONDS", 0.1)
    fake = _Fake()
    codes: list[int] = []
    thread = threading.Thread(target=lambda: codes.append(scout_host.serve(fake, idle=0.3)))
    yield fake, thread, codes
    for lemon_id in scout_roster.listed():
        scout_roster.remove(lemon_id)  # an exiting host with registrations left re-execs
    thread.join(10)
    assert not thread.is_alive()


def test_a_scout_that_ends_removes_its_registration_and_the_idle_host_exits(host):
    fake, thread, codes = host
    registration = scout_roster.register("task.IndexElf", "claude:abcd1234", "", "/work")
    thread.start()
    _until(lambda: fake.started == [registration])
    assert scout_roster.host_pid() and any(w.kind == "host" for w in registry.running())

    fake.outcomes["task.IndexElf"] = "ended"

    thread.join(10)
    assert codes == [0]
    assert scout_roster.read("task.IndexElf") is None
    assert not scout_roster.host_pid()


def test_a_replaced_registration_stops_the_old_scout_and_starts_the_new(host):
    fake, thread, _ = host
    old = scout_roster.register("task.IndexElf", "claude:00000000", "", "/work")
    thread.start()
    _until(lambda: fake.started == [old])

    new = scout_roster.register("task.IndexElf", "claude:abcd1234", "", "/work")

    _until(lambda: fake.started == [old, new])
    assert fake.stopped == [old.token]
    scout_roster.remove("task.IndexElf")
    _until(lambda: fake.stopped == [old.token, new.token])


def test_a_failed_or_crashed_scout_is_tried_again(host):
    fake, thread, _ = host
    registration = scout_roster.register("task.IndexElf", "codex:t", "t", "/work")
    fake.outcomes["task.IndexElf"] = "retry"
    thread.start()
    _until(lambda: len(fake.started) == 2)

    fake.outcomes["task.IndexElf"] = "crash"

    _until(lambda: len(fake.started) == 3)
    assert set(fake.started) == {registration}


def test_a_registration_from_another_environment_is_left_alone(host, tmp_path):
    fake, thread, codes = host
    registration = scout_roster.register("task.IndexElf", "claude:abcd1234", "", "/work")
    path = tmp_path / "state" / "scouts" / "task.IndexElf.json"
    path.write_text(
        json.dumps({**registration._asdict(), "environment": json.dumps(["/elsewhere.db"])})
    )
    thread.start()

    thread.join(10)
    assert codes == [0] and fake.started == []
    path.unlink()


def test_a_second_host_refuses_to_start(host):
    fake, thread, _ = host
    scout_roster.register("task.IndexElf", "claude:abcd1234", "", "/work")
    thread.start()
    _until(lambda: fake.started)

    assert scout_host.serve(fake) == 3
    fake.outcomes["task.IndexElf"] = "ended"
