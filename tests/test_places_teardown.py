"""Teardown has to move you out before it removes anything.

The caller is usually standing inside the directory being destroyed, and the
removal is slow, so the order is: check, switch away, then do the work detached.
"""

import shutil
import subprocess
import time
import uuid

import pytest

from lemonaid.config import PlaceRoot
from lemonaid.inbox import db
from lemonaid.places import ownership, teardown


def _destroyable(path) -> PlaceRoot:
    return PlaceRoot(path=path, destroy="release {key}")


def _place(tmp_path, key: str = "k", root: PlaceRoot | None = None) -> ownership.Place:
    """A place whose directory actually exists, so it is worth releasing."""
    directory = tmp_path / key
    directory.mkdir(parents=True, exist_ok=True)

    return ownership.Place(key, root or _destroyable(tmp_path), directory)


def test_toss_does_not_tear_down_if_a_client_cannot_escape(monkeypatch, tmp_path):
    monkeypatch.setattr(teardown.escape, "evacuate", lambda session: "Nowhere to switch")
    spawned = []
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: spawned.append(a))

    assert teardown.toss("doomed", [_place(tmp_path)]) == "Nowhere to switch"
    assert not spawned


def test_toss_without_a_session_switches_nothing(monkeypatch, tmp_path):
    """There is no session being killed, so no client is standing in danger."""
    evacuated = []
    monkeypatch.setattr(teardown.escape, "evacuate", lambda session: evacuated.append(session))
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    assert teardown.toss("", [_place(tmp_path)]) is None
    assert not evacuated


def test_toss_switches_away_before_spawning_the_reaper(monkeypatch, tmp_path):
    order = []

    def _evacuate(session):
        order.append("evacuate")
        return ""

    def _reap(*args):
        order.append("reap")
        return None

    monkeypatch.setattr(teardown.escape, "evacuate", _evacuate)
    monkeypatch.setattr(teardown, "_spawn_reaper", _reap)

    assert teardown.toss("doomed", [_place(tmp_path)]) is None
    assert order == ["evacuate", "reap"]


def test_toss_of_a_session_with_no_places_is_just_a_kill(monkeypatch, tmp_path):
    """Sometimes there is no worktree, and closing the session is the whole ask."""
    captured = {}

    def _run(argv, **kwargs):
        captured["script"] = argv[-1]

        class _Result:
            returncode = 0
            stdout = ""

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    assert teardown.toss("notes", []) is None
    assert "kill-session -t =notes" in captured["script"]


def _reaper_script(monkeypatch, session: str, places, cwd) -> str:
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0
            stdout = ""

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)
    teardown._spawn_reaper(session, places, cwd)

    return captured["argv"][-1]


def test_reaper_kills_the_session_before_releasing_the_directory(monkeypatch, tmp_path):
    """A process holding a file in the directory can make its removal fail."""
    script = _reaper_script(monkeypatch, "doomed", [_place(tmp_path, "mykey")], tmp_path)

    assert script.index("kill-session") < script.index("release")


def test_reaper_releases_every_place_the_session_owned(monkeypatch, tmp_path):
    """The point of the whole thing: no place is left behind when its session dies."""
    script = _reaper_script(
        monkeypatch, "stacked", [_place(tmp_path, "base"), _place(tmp_path, "on-top")], tmp_path
    )

    assert "release base" in script
    assert "release on-top" in script


def test_reaper_releases_without_a_session_to_kill(monkeypatch, tmp_path):
    """An acquired directory nobody opened has nothing to kill, only to release."""
    script = _reaper_script(monkeypatch, "", [_place(tmp_path, "lonely")], tmp_path)

    assert "kill-session -t =lonely" not in script
    assert script.endswith("tmux kill-session -t =_lma_reap_lonely")
    assert "release lonely" in script


def test_reaper_names_itself_after_the_places_when_there_is_no_session(monkeypatch, tmp_path):
    """Two sessionless tosses at once would otherwise ask tmux for the same name."""
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0
            stdout = ""

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)
    teardown._spawn_reaper("", [_place(tmp_path, "lonely")], tmp_path)

    assert "lonely" in captured["argv"][captured["argv"].index("-s") + 1]


def test_reaper_skips_a_place_whose_directory_is_already_gone(monkeypatch, tmp_path):
    """Not a failure - it's the normal state for a session outliving its worktree."""
    gone = ownership.Place("vanished", _destroyable(tmp_path), tmp_path / "vanished")
    script = _reaper_script(monkeypatch, "ghost", [_place(tmp_path, "real"), gone], tmp_path)

    assert "release real" in script
    assert "release vanished" not in script


def test_reaper_skips_a_place_whose_root_cannot_release(monkeypatch, tmp_path):
    """A plain clone has a session but nothing to release."""
    plain = _place(tmp_path, "clone", root=PlaceRoot(path=tmp_path))
    script = _reaper_script(monkeypatch, "doomed", [plain], tmp_path)

    assert "kill-session -t =doomed" in script
    assert "release" not in script


def test_reaper_session_name_is_recognizable_and_deterministic():
    """A stuck teardown has to be findable in `tmux ls`."""
    assert teardown._reaper_session_name("protostellar/enums") == "_lma_reap_protostellar-enums"


def test_reaper_does_not_sit_in_a_directory_it_is_removing(monkeypatch, tmp_path):
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0
            stdout = ""

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    teardown.toss("doomed", [_place(tmp_path, "feat")])

    assert captured["argv"][captured["argv"].index("-c") + 1] == str(tmp_path)


def test_concerns_come_from_the_inspect_hook(tmp_path):
    place = _place(tmp_path, "k", root=PlaceRoot(path=tmp_path, inspect="echo 3 dirty"))

    assert teardown.concerns(place) == ["3 dirty"]


def test_no_concerns_when_inspect_says_nothing(tmp_path):
    assert (
        teardown.concerns(_place(tmp_path, "k", root=PlaceRoot(path=tmp_path, inspect="true")))
        == []
    )


def test_a_vanished_directory_has_no_concerns(tmp_path):
    """It can't be holding work you haven't pushed."""
    gone = ownership.Place("gone", PlaceRoot(path=tmp_path, inspect="echo 3 dirty"), tmp_path / "x")

    assert teardown.concerns(gone) == []


def test_reaper_passes_the_shell_and_its_flag_as_separate_arguments(monkeypatch, tmp_path):
    """tmux execs the command itself rather than handing it to a shell.

    A single "sh -c ..." string is looked up as a program by that literal name,
    so the reaper session dies instantly and nothing runs - silently, since there
    is no terminal anyone sees.
    """
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0
            stdout = ""

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    teardown._spawn_reaper("doomed", [_place(tmp_path)], tmp_path)

    argv = captured["argv"]
    assert argv[-3:-1] == ["sh", "-c"]
    assert "kill-session" in argv[-1]


def test_reaper_disappears_with_global_remain_on_exit_on(monkeypatch, tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-reaper-test-{uuid.uuid4().hex[:8]}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    started = tmux("-f", "/dev/null", "new-session", "-d", "-s", "doomed", "sleep", "30")
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    socket = tmux("display-message", "-p", "-t", "doomed", "#{socket_path}").stdout.strip()
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    monkeypatch.setattr(teardown, "reap_log_path", lambda: tmp_path / "reap.log")
    try:
        assert tmux("set-option", "-g", "remain-on-exit", "on").returncode == 0
        assert teardown._spawn_reaper("doomed", [], tmp_path) is None

        deadline = time.monotonic() + 3
        while tmux("has-session", "-t", "_lma_reap_doomed").returncode == 0:
            assert time.monotonic() < deadline, "reaper session did not remove itself"
            time.sleep(0.05)

        assert tmux("has-session", "-t", "doomed").returncode != 0
        assert "--- done doomed ---" in (tmp_path / "reap.log").read_text()
    finally:
        tmux("kill-server")


def test_reaper_does_not_kill_a_prefix_named_session(monkeypatch, tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-reaper-test-{uuid.uuid4().hex[:8]}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    started = tmux("-f", "/dev/null", "new-session", "-d", "-s", "doomed-sibling", "sleep", "30")
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    socket = tmux("display-message", "-p", "-t", "doomed-sibling", "#{socket_path}").stdout.strip()
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    monkeypatch.setattr(teardown, "reap_log_path", lambda: tmp_path / "reap.log")
    try:
        assert tmux("set-option", "-g", "remain-on-exit", "on").returncode == 0
        assert teardown._spawn_reaper("doomed", [], tmp_path) is None

        deadline = time.monotonic() + 3
        while tmux("has-session", "-t", "=_lma_reap_doomed").returncode == 0:
            assert time.monotonic() < deadline, "reaper session did not remove itself"
            time.sleep(0.05)

        assert tmux("has-session", "-t", "=doomed-sibling").returncode == 0
        assert "--- done doomed ---" in (tmp_path / "reap.log").read_text()
    finally:
        tmux("kill-server")


def _lemon(channel: str, cwd, tty: str | None = None) -> None:
    metadata = {"cwd": str(cwd), **({"tty": tty} if tty else {})}
    with db.connect() as conn:
        db.add(conn, channel=channel, message="waiting", metadata=metadata)


def _active_channels() -> set[str]:
    with db.connect() as conn:
        return {n.channel for n in db.get_active(conn)}


def _session_panes(monkeypatch, ttys: set[str]) -> None:
    """*ttys* are the doomed session's panes, and no client is watching it."""
    monkeypatch.setattr(teardown.tmux.navigation, "session_ttys", lambda session: ttys)
    monkeypatch.setattr(teardown.escape, "evacuate", lambda session: "")


def test_toss_archives_the_lemons_in_a_released_place(monkeypatch, tmp_path):
    """Including a Codex row with no tty, which the watcher cannot place."""
    place = _place(tmp_path, "review")
    (place.directory / "sub").mkdir()
    _lemon("codex:reviewer", place.directory)
    _lemon("claude:author", place.directory / "sub")
    _lemon("claude:elsewhere", tmp_path / "other")
    _session_panes(monkeypatch, set())
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    assert teardown.toss("review", [place]) is None
    assert _active_channels() == {"claude:elsewhere"}


def test_toss_archives_the_lemons_on_the_killed_sessions_panes(monkeypatch, tmp_path):
    """With no place released at all, as for a place whose root keeps its directory."""
    _lemon("claude:window-2", tmp_path, tty="/dev/ttys041")
    _lemon("claude:elsewhere", tmp_path, tty="/dev/ttys042")
    _session_panes(monkeypatch, {"/dev/ttys041"})
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    teardown.toss("review", [])

    assert _active_channels() == {"claude:elsewhere"}


def test_toss_keeps_a_codex_row_whose_tty_is_on_the_killed_session(monkeypatch, tmp_path):
    """Older rows under the app-server recorded the tty of the TUI that started it."""
    _lemon("codex:elsewhere", tmp_path / "other", tty="/dev/ttys012")
    _session_panes(monkeypatch, {"/dev/ttys012"})
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    teardown.toss("docs", [])

    assert _active_channels() == {"codex:elsewhere"}


def test_toss_keeps_no_tty_lemons_in_a_place_it_does_not_destroy(monkeypatch, tmp_path):
    """Its directory stays, and another session may be working in it."""
    place = _place(tmp_path, "plain", PlaceRoot(path=tmp_path))
    _lemon("codex:reviewer", place.directory)
    _session_panes(monkeypatch, set())
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    teardown.toss("plain", [place])

    assert _active_channels() == {"codex:reviewer"}


def test_a_reaper_that_finishes_first_still_leaves_its_rows_archived(monkeypatch, tmp_path):
    place = _place(tmp_path, "review")
    _lemon("codex:reviewer", place.directory)
    _session_panes(monkeypatch, set())
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: shutil.rmtree(place.directory))

    teardown.toss("review", [place])

    assert _active_channels() == set()


def test_a_failed_toss_archives_nothing(monkeypatch, tmp_path):
    place = _place(tmp_path, "review")
    _lemon("codex:reviewer", place.directory)
    _session_panes(monkeypatch, set())
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: "Could not start teardown")

    assert teardown.toss("review", [place])
    assert _active_channels() == {"codex:reviewer"}
