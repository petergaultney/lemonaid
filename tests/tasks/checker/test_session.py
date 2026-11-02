import concurrent.futures
import sys
import time

import pytest

from lemonaid.tasks.checker import protocol, replay, session

from ..shared import NOW


def _input() -> str:
    return protocol.render(
        [
            ("context", "now", NOW),
            ("task", "t1", "holder", "brief:Work.alpha"),
            ("task", "t1", "lifecycle", "closed"),
            ("task", "t1", "revision", "3"),
        ]
    )


def test_one_default_checker_process_answers_every_request():
    with session.Session(replay.DEFAULT_CHECKER, 30) as checker:
        described = checker.ask("describe", _input())
        evaluated = checker.ask("evaluate", _input())
        first = checker._process

        assert checker.ask("evaluate", _input()) == evaluated and checker._process is first
    assert ("watch", "task", "t1") in protocol.parse(described, protocol.DESCRIBE)
    assert protocol.parse(evaluated, protocol.EVALUATE)[0][1] == "t1"


def test_a_request_the_checker_rejects_fails_and_the_process_carries_on():
    with session.Session(replay.DEFAULT_CHECKER, 30) as checker:
        with pytest.raises(session.Failed):
            checker.ask("evaluate", "not the protocol")

        assert checker.ask("evaluate", _input())


def test_a_checker_that_exits_or_hangs_fails_its_requests_and_is_started_again():
    exits = session.Session((sys.executable, "-c", "import sys"), 5)
    with exits, pytest.raises(session.Failed, match="exited"):
        exits.ask("evaluate", _input())
    hangs = session.Session((sys.executable, "-c", "import time; time.sleep(30)"), 0.5)
    with hangs, pytest.raises(session.Failed, match="no answer"):
        hangs.ask("evaluate", _input())


def test_a_checker_that_never_reads_still_fails_by_the_deadline():
    stuck = session.Session((sys.executable, "-c", "import time; time.sleep(30)"), 0.1)
    started = time.monotonic()

    with stuck, pytest.raises(session.Failed, match="no answer"):
        stuck.ask("evaluate", "x" * 1_000_000)  # far more than a pipe holds

    assert time.monotonic() - started < 3


def test_an_old_checker_exiting_leaves_its_replacements_requests_waiting():
    with session.Session(replay.DEFAULT_CHECKER, 30) as checker:
        checker.ask("describe", _input())
        old = checker._process
        newer: concurrent.futures.Future[str] = concurrent.futures.Future()
        checker._waiting["later"] = (object(), newer)  # sent to the process that replaced it

        old.kill()
        deadline = time.monotonic() + 5
        while checker._process is old and time.monotonic() < deadline:
            time.sleep(0.01)

        assert checker._process is None and not newer.done()
        checker._waiting.clear()
