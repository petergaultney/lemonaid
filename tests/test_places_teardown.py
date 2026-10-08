"""Teardown has to move you out before it removes anything.

The caller is usually standing inside the directory being destroyed, and the
removal is slow, so the order is: check, switch away, then do the work detached.
"""

import shutil
import subprocess
import time
import uuid
from types import SimpleNamespace

import pytest

from lemonaid.brief import attached
from lemonaid.config import PlaceRoot
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.lemon_watchers import watcher
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
        db.add(conn, channel=channel, message="waiting", metadata=metadata, switch_source="tmux")


def _active_channels() -> set[str]:
    with db.connect() as conn:
        return {n.channel for n in db.get_active(conn)}


def _watcher_tick(monkeypatch, locations, protected_status=""):
    protected = set()
    if protected_status:
        monkeypatch.setattr(
            attached,
            "by_channel",
            lambda conn, channels: {channel: channel for channel in channels},
        )
        app = SimpleNamespace(
            _brief_cache={
                channel: SimpleNamespace(status=protected_status) for channel in _active_channels()
            }
        )
        protected = LemonaidApp._protected_brief_channels(app)
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)
    with db.connect() as conn:
        rows = db.get_active(conn)
    active = [
        (
            n.channel,
            "",
            n.metadata.get("cwd", ""),
            n.created_at,
            True,
            n.metadata.get("tty"),
            n.message,
            n.switch_source,
        )
        for n in rows
    ]

    def archive(channel):
        with db.connect() as conn:
            db.archive_channel(conn, channel, "watcher")

    return watcher._archive_stale_sessions(
        active, archive, {}, {None: locations}, protected_channels=protected
    )


def _session_panes(monkeypatch, ttys: set[str]) -> None:
    """*ttys* are the doomed session's panes, and no client is watching it."""
    monkeypatch.setattr(teardown.tmux.navigation, "session_ttys", lambda session: ttys)
    monkeypatch.setattr(teardown.escape, "evacuate", lambda session: "")
    monkeypatch.setattr(
        teardown.tmux.navigation,
        "locations_by_tty",
        lambda socket: {tty: teardown.tmux.navigation.PaneLocation("review", "1") for tty in ttys},
    )


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
    assert _active_channels() == {"claude:elsewhere", "claude:author"}


def test_toss_archives_the_lemons_on_the_killed_sessions_panes(monkeypatch, tmp_path):
    """With no place released at all, as for a place whose root keeps its directory."""
    _lemon("claude:window-2", tmp_path, tty="/dev/ttys041")
    _lemon("claude:elsewhere", tmp_path, tty="/dev/ttys042")
    _session_panes(monkeypatch, {"/dev/ttys041"})
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    teardown.toss("review", [])

    assert _active_channels() == {"claude:window-2", "claude:elsewhere"}
    _watcher_tick(
        monkeypatch, {"/dev/ttys042": teardown.tmux.navigation.PaneLocation("elsewhere", "1")}
    )
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


def _pane(session: str, window: str, pane: str, path) -> ownership.Pane:
    return ownership.Pane(session, window, pane, path)


def _partial_stubs(monkeypatch, *, moved: str = "", own: str = "") -> dict:
    """Stub every tmux-facing step of a partial toss, recording what was asked."""
    asked: dict = {"closed": [], "reaper": None}
    monkeypatch.setattr(teardown.windows, "move_clients_off", lambda doomed: moved)
    monkeypatch.setattr(teardown.windows, "own_window", lambda: own)
    monkeypatch.setattr(teardown.windows, "ttys", lambda ws: set())
    monkeypatch.setattr(teardown.windows, "close", lambda ws: asked["closed"].extend(ws) or [])
    monkeypatch.setattr(
        teardown,
        "_spawn_reaper",
        lambda *args: asked.__setitem__("reaper", args) or None,
    )
    return asked


def test_a_client_that_cannot_be_moved_stops_a_partial_toss(monkeypatch, tmp_path):
    asked = _partial_stubs(monkeypatch, moved="Nowhere to move it")
    partial = {"@4": [_pane("k", "@4", "%4", tmp_path)]}

    assert teardown.toss("", [_place(tmp_path)], partial) == "Nowhere to move it"
    assert asked["closed"] == []
    assert asked["reaper"] is None


def test_partial_windows_close_before_the_reaper_releases(monkeypatch, tmp_path):
    asked = _partial_stubs(monkeypatch)
    partial = {"@4": [_pane("k", "@4", "%4", tmp_path)], "@7": [_pane("k", "@7", "%7", tmp_path)]}

    assert teardown.toss("", [_place(tmp_path)], partial) is None

    assert asked["closed"] == ["@4", "@7"]
    session, places, _cwd, window = asked["reaper"]
    assert session == ""
    assert [p.key for p in places] == ["k"]
    assert window == ""


def test_the_callers_own_window_is_left_to_the_reaper(monkeypatch, tmp_path):
    """Closing it here would end this process before the directory is released."""
    asked = _partial_stubs(monkeypatch, own="@7")
    partial = {"@4": [_pane("k", "@4", "%4", tmp_path)], "@7": [_pane("k", "@7", "%7", tmp_path)]}

    assert teardown.toss("", [_place(tmp_path)], partial) is None

    assert asked["closed"] == ["@4"]
    assert asked["reaper"][3] == "@7"


def test_an_own_window_outside_the_plan_is_not_touched(monkeypatch, tmp_path):
    asked = _partial_stubs(monkeypatch, own="@1")
    partial = {"@4": [_pane("k", "@4", "%4", tmp_path)]}

    assert teardown.toss("", [_place(tmp_path)], partial) is None

    assert asked["closed"] == ["@4"]
    assert asked["reaper"][3] == ""


def test_a_window_that_will_not_close_keeps_the_directory(monkeypatch, tmp_path):
    asked = _partial_stubs(monkeypatch)
    monkeypatch.setattr(teardown.windows, "close", lambda ws: ["@4"])
    partial = {"@4": [_pane("k", "@4", "%4", tmp_path)]}

    error = teardown.toss("", [_place(tmp_path)], partial)

    assert error is not None and "@4" in error and "not released" in error
    assert asked["reaper"] is None


def test_a_toss_with_no_partial_windows_asks_tmux_nothing_about_them(monkeypatch, tmp_path):
    """The whole-session path is untouched by the window machinery."""
    monkeypatch.setattr(teardown.escape, "evacuate", lambda session: "")
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    def _never(*args):  # pragma: no cover - reached only on a regression
        raise AssertionError("partial-window step ran for a whole-session toss")

    monkeypatch.setattr(teardown.windows, "move_clients_off", _never)
    monkeypatch.setattr(teardown.windows, "close", _never)

    assert teardown.toss("doomed", [_place(tmp_path)]) is None


def test_the_reaper_kills_the_callers_window_before_releasing(monkeypatch, tmp_path):
    captured = {}

    def _run(argv, **kwargs):
        captured["script"] = argv[-1]
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    teardown._spawn_reaper("", [_place(tmp_path)], tmp_path, "@7")

    script = captured["script"]
    assert script.count("kill-session") == 1  # only the reaper killing itself at the end
    assert script.index("kill-window -t @7") < script.index("release k")


def test_toss_leaves_closing_window_rows_to_the_watcher(monkeypatch, tmp_path):
    _partial_stubs(monkeypatch)
    _lemon("claude:on-window", "/x", tty="/dev/ttys004")
    _lemon("claude:elsewhere", "/x", tty="/dev/ttys009")
    assert teardown.toss("", [], {"@4": []}) is None
    assert _active_channels() == {"claude:on-window", "claude:elsewhere"}
    _watcher_tick(
        monkeypatch, {"/dev/ttys009": teardown.tmux.navigation.PaneLocation("elsewhere", "1")}
    )
    assert _active_channels() == {"claude:elsewhere"}


def test_a_partial_toss_closes_only_the_planned_windows(monkeypatch, tmp_path):
    """On a real tmux server: the shared session keeps its other windows and its client."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-partial-test-{uuid.uuid4().hex[:8]}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    merged, live = tmp_path / "feat" / "merged", tmp_path / "feat" / "live"
    merged.mkdir(parents=True)
    live.mkdir(parents=True)
    started = tmux("-f", "/dev/null", "new-session", "-d", "-s", "katamari", "-c", str(live))
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    tmux("new-window", "-d", "-t", "katamari", "-c", str(merged))
    tmux("new-window", "-d", "-t", "katamari", "-c", str(merged))
    tmux("new-session", "-d", "-s", "other", "-c", str(merged))
    socket = tmux("display-message", "-p", "-t", "katamari", "#{socket_path}").stdout.strip()
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr(teardown, "reap_log_path", lambda: tmp_path / "reap.log")
    try:
        panes = [p for p in ownership.panes() if p.path and p.path.resolve() == merged.resolve()]
        doomed = {w: [p for p in panes if p.window == w] for w in {p.window for p in panes}}
        assert len(doomed) == 3
        kept = [p.window for p in ownership.panes() if p.window not in doomed]
        assert len(kept) == 1
        root = PlaceRoot(path=tmp_path, destroy="echo released {key}")
        place = ownership.Place("feat/merged", root, merged)

        assert teardown.toss("", [place], doomed) is None

        deadline = time.monotonic() + 3
        while tmux("has-session", "-t", "=_lma_reap_feat-merged").returncode == 0:
            assert time.monotonic() < deadline, "reaper session did not remove itself"
            time.sleep(0.05)

        remaining = [p.window for p in ownership.panes()]
        assert remaining == kept
        assert tmux("has-session", "-t", "=katamari").returncode == 0
        assert "released feat/merged" in (tmp_path / "reap.log").read_text()
    finally:
        tmux("kill-server")


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_toss_keeps_a_pinned_lemon_in_a_surviving_pane_inside_the_place(
    monkeypatch, tmp_path, harness
):
    place = _place(tmp_path, "child")
    with db.connect() as conn:
        db.add(
            conn,
            channel=f"{harness}:lead",
            message="waiting",
            switch_source="tmux",
            metadata={
                "cwd": str(place.directory),
                "tty": "/dev/lead",
                "tmux_session_order": [1, 1, 1],
                "tmux_pane_identity": ["%1", 1],
            },
        )
    _lemon("claude:child", place.directory, tty="/dev/child")
    _session_panes(monkeypatch, {"/dev/child"})
    monkeypatch.setattr(
        teardown.tmux.navigation,
        "locations_by_tty",
        lambda socket: {
            "/dev/lead": teardown.tmux.navigation.PaneLocation("lead", "1", (1, 1, 1)),
            "/dev/child": teardown.tmux.navigation.PaneLocation("child", "1"),
        },
    )
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)
    with db.connect() as conn:
        lead = next(n for n in db.get_active(conn) if n.channel == f"{harness}:lead")
        conn.execute("INSERT INTO pins (channel, position) VALUES (?, 0)", (lead.channel,))
        conn.commit()

    assert teardown.toss("child", [place]) is None
    assert _active_channels() == {f"{harness}:lead", "claude:child"}
    _watcher_tick(
        monkeypatch, {"/dev/lead": teardown.tmux.navigation.PaneLocation("lead", "1", (1, 1, 1))}
    )
    with db.connect() as conn:
        remaining = db.get_active(conn)
        assert [n.channel for n in remaining] == [f"{harness}:lead"]
        assert conn.execute("SELECT channel FROM pins").fetchall()[0][0] == f"{harness}:lead"


def test_toss_archives_legacy_codex_daemon_rows_in_the_released_directory(monkeypatch, tmp_path):
    place = _place(tmp_path)
    _lemon("codex:legacy", place.directory, tty="/daemon")
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)
    assert teardown.toss("", [place]) is None
    assert _active_channels() == set()


def test_toss_then_watcher_archives_identified_codex_without_directory_release(
    monkeypatch, tmp_path
):
    with db.connect() as conn:
        db.add(
            conn,
            channel="codex:cli",
            message="waiting",
            switch_source="tmux",
            metadata={
                "cwd": str(tmp_path),
                "tty": "/cli",
                "tmux_session_order": [1, 1, 1],
                "tmux_pane_identity": ["%1", 1],
            },
        )
    _session_panes(monkeypatch, {"/cli"})
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)
    assert teardown.toss("cli", []) is None
    assert _active_channels() == {"codex:cli"}
    _watcher_tick(monkeypatch, {})
    assert _active_channels() == set()


@pytest.mark.parametrize("status", ["merge", "approve", "blocked", "alert"])
@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_watcher_honors_toss_evidence_for_protected_rows(
    monkeypatch, tmp_path, status, partial, harness
):
    with db.connect() as conn:
        db.add(
            conn,
            channel=f"{harness}:closing",
            message="waiting",
            switch_source="tmux",
            metadata={
                "tty": "/closing",
                "tmux_session_order": [1, 1, 1],
                "tmux_pane_identity": ["%1", 1],
            },
        )
    _lemon("claude:surviving", tmp_path, tty="/surviving")
    if partial:
        _partial_stubs(monkeypatch)
        monkeypatch.setattr(teardown.windows, "ttys", lambda windows: {"/closing"})
        assert teardown.toss("", [], {"@4": []}) is None
    else:
        _session_panes(monkeypatch, {"/closing"})
        monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)
        assert teardown.toss("closing", []) is None
    assert _active_channels() == {f"{harness}:closing", "claude:surviving"}
    _watcher_tick(
        monkeypatch,
        {
            "/closing": teardown.tmux.navigation.PaneLocation("closing", "1", (1, 1, 1)),
            "/surviving": teardown.tmux.navigation.PaneLocation("surviving", "1"),
        },
        status,
    )
    assert _active_channels() == {f"{harness}:closing", "claude:surviving"}
    _watcher_tick(
        monkeypatch, {"/surviving": teardown.tmux.navigation.PaneLocation("surviving", "1")}, status
    )
    assert _active_channels() == {"claude:surviving"}


def test_failed_teardown_records_no_terminal_evidence(monkeypatch, tmp_path):
    _lemon("claude:closing", tmp_path, tty="/closing")
    _session_panes(monkeypatch, {"/closing"})
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: "failed")
    assert teardown.toss("closing", []) == "failed"
    _watcher_tick(monkeypatch, {}, "blocked")
    assert _active_channels() == {"claude:closing"}


def test_toss_evidence_does_not_override_another_servers_brief(monkeypatch, tmp_path):
    with db.connect() as conn:
        db.add(
            conn,
            channel="claude:other",
            message="waiting",
            switch_source="tmux",
            metadata={"tty": "/closing", "tmux_socket": "/other"},
        )
    _session_panes(monkeypatch, {"/closing"})
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)
    assert teardown.toss("closing", []) is None
    _watcher_tick(monkeypatch, {}, "blocked")
    assert _active_channels() == {"claude:other"}
