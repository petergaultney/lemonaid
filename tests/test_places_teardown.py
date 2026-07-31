"""Teardown has to move you out before it removes anything.

The caller is usually standing inside the directory being destroyed, and the
removal is slow, so the order is: check, switch away, then do the work detached.
"""

from lemonaid.config import PlaceRoot
from lemonaid.places import ownership, teardown


def _destroyable(path) -> PlaceRoot:
    return PlaceRoot(path=path, destroy="release {key}")


def _place(tmp_path, key: str = "k", root: PlaceRoot | None = None) -> ownership.Place:
    """A place whose directory actually exists, so it is worth releasing."""
    directory = tmp_path / key
    directory.mkdir(parents=True, exist_ok=True)

    return ownership.Place(key, root or _destroyable(tmp_path), directory)


def _tmux_sessions(monkeypatch, listing: str) -> None:
    def _run(argv, **kwargs):
        class _Result:
            stdout = listing
            returncode = 0

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)


def test_escape_target_prefers_where_you_came_from(monkeypatch):
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: ("earlier", "%1"))

    assert teardown._escape_target("doomed") == "earlier"


def test_escape_target_ignores_a_back_location_that_is_the_doomed_session(monkeypatch):
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: ("doomed", "%1"))
    _tmux_sessions(monkeypatch, "100 older\n200 newer\n300 doomed\n")

    assert teardown._escape_target("doomed") == "newer"


def test_escape_target_falls_back_to_most_recently_active(monkeypatch):
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 older\n300 newest\n200 middle\n")

    assert teardown._escape_target("doomed") == "newest"


def test_escape_target_skips_lemonaid_internal_sessions(monkeypatch):
    """The scratch pane and reapers are not places to be dropped into."""
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 real\n900 _lma_scratch\n800 _lma_reap_x\n")

    assert teardown._escape_target("doomed") == "real"


def test_escape_target_empty_when_nowhere_to_go(monkeypatch):
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 doomed\n")

    assert teardown._escape_target("doomed") == ""


def test_toss_from_inside_refuses_when_there_is_nowhere_to_go(monkeypatch, tmp_path):
    """Killing the session you're in with no destination would strand the client."""
    monkeypatch.setattr(teardown, "_escape_target", lambda session: "")
    spawned = []
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: spawned.append(a))

    error = teardown.toss("doomed", [_place(tmp_path)], from_inside=True)

    assert error and "Nowhere to switch to" in error
    assert not spawned


def test_toss_does_not_tear_down_if_the_escape_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(teardown, "_escape_target", lambda session: "elsewhere")
    monkeypatch.setattr(teardown, "_switch_client", lambda session: False)
    spawned = []
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: spawned.append(a))

    error = teardown.toss("doomed", [_place(tmp_path)], from_inside=True)

    assert error and "nothing was torn down" in error
    assert not spawned


def test_toss_switches_away_before_spawning_the_reaper(monkeypatch, tmp_path):
    order = []

    def _switch(session):
        order.append("switch")
        return True

    def _reap(*args):
        order.append("reap")
        return None

    monkeypatch.setattr(teardown, "_escape_target", lambda session: "elsewhere")
    monkeypatch.setattr(teardown, "_switch_client", _switch)
    monkeypatch.setattr(teardown, "_spawn_reaper", _reap)

    assert teardown.toss("doomed", [_place(tmp_path)], from_inside=True) is None
    assert order == ["switch", "reap"]


def test_toss_from_outside_does_not_switch_anything(monkeypatch, tmp_path):
    """Tearing down something you aren't in needs no escape."""
    switched = []

    def _switch(session):
        switched.append(session)
        return True

    monkeypatch.setattr(teardown, "_switch_client", _switch)
    monkeypatch.setattr(teardown, "_spawn_reaper", lambda *a: None)

    assert teardown.toss("other", [_place(tmp_path)], from_inside=False) is None
    assert not switched


def test_toss_of_a_session_with_no_places_is_just_a_kill(monkeypatch, tmp_path):
    """Sometimes there is no worktree, and closing the session is the whole ask."""
    monkeypatch.setattr(teardown, "_switch_client", lambda session: True)
    monkeypatch.setattr(teardown, "_escape_target", lambda session: "elsewhere")
    captured = {}

    def _run(argv, **kwargs):
        captured["script"] = argv[-1]

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    assert teardown.toss("notes", [], from_inside=True) is None
    assert "kill-session -t notes" in captured["script"]


def _reaper_script(monkeypatch, session: str, places, cwd) -> str:
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = argv

        class _Result:
            returncode = 0

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

    assert "kill-session -t doomed" in script
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

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    teardown.toss("doomed", [_place(tmp_path, "feat")], from_inside=False)

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

        return _Result()

    monkeypatch.setattr(teardown.subprocess, "run", _run)

    teardown._spawn_reaper("doomed", [_place(tmp_path)], tmp_path)

    argv = captured["argv"]
    assert argv[-3:-1] == ["sh", "-c"]
    assert "kill-session" in argv[-1]


def test_escape_prefers_a_session_that_wants_attention(monkeypatch):
    """The most recently active session is often the one you just left."""
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "300 just-left\n100 waiting-on-you\n")
    monkeypatch.setattr(teardown, "_wants_attention", lambda available: "waiting-on-you")

    assert teardown._escape_target("doomed") == "waiting-on-you"


def test_escape_falls_back_to_recency_when_nothing_is_waiting(monkeypatch):
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 older\n300 newest\n")
    monkeypatch.setattr(teardown, "_wants_attention", lambda available: "")

    assert teardown._escape_target("doomed") == "newest"


def test_attention_only_counts_sessions_that_are_actually_live(monkeypatch):
    """An archived notification may name a session that no longer exists."""
    monkeypatch.setattr(teardown.tmux.navigation, "load_back_location", lambda: (None, None))
    _tmux_sessions(monkeypatch, "100 live-one\n")

    class _N:
        name = "long-gone"

    monkeypatch.setattr(teardown.db, "get_unread", lambda conn: [_N()])

    assert teardown._escape_target("doomed") == "live-one"
