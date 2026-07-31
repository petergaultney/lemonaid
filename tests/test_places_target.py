"""Working out what `place toss` should tear down.

The unit is a session and everything it occupies. A key is a way of naming a
session, not a separate mode - so both forms resolve to the same set, and there
is no form that kills a session while stranding places it owned.
"""

from pathlib import Path

from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.places import ownership, target


def _root(tmp_path: Path) -> PlaceRoot:
    return PlaceRoot(
        path=tmp_path,
        list=f"find {tmp_path} -name .git -exec dirname {{}} \\;",
        path_of=f"echo {tmp_path}/{{key}}",
    )


def _managed(tmp_path: Path, *keys: str) -> None:
    for key in keys:
        (tmp_path / key / ".git").mkdir(parents=True)


def _panes(monkeypatch, **by_session: list[Path]) -> None:
    monkeypatch.setattr(
        target.ownership, "pane_paths", lambda: {k: list(v) for k, v in by_session.items()}
    )


def _attached_to(monkeypatch, session: str | None) -> None:
    monkeypatch.setattr(
        target.tmux.navigation,
        "get_current_location",
        lambda: (session, "%1" if session else None),
    )


def _config(*roots: PlaceRoot) -> Config:
    return Config(places=PlacesConfig(roots=list(roots)))


def test_unnamed_toss_is_the_session_you_are_attached_to(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, work=[tmp_path / "feat"])
    _attached_to(monkeypatch, "work")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "work"
    assert [p.key for p in doomed.places] == ["feat"]
    assert doomed.from_inside is True


def test_unnamed_toss_works_from_a_window_that_wandered(monkeypatch, tmp_path):
    """Your session is your session; where a window happens to sit doesn't change it.

    The directory you're standing in used to make this ambiguous. Under
    session-first ownership it doesn't: the set comes from the session's panes.
    """
    _managed(tmp_path, "mine", "elsewhere")
    _panes(monkeypatch, mine=[tmp_path / "mine"], other=[tmp_path / "elsewhere"])
    _attached_to(monkeypatch, "mine")
    monkeypatch.chdir(tmp_path / "elsewhere")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "mine"
    assert [p.key for p in doomed.places] == ["mine"]


def test_unnamed_toss_needs_tmux(monkeypatch, tmp_path):
    _attached_to(monkeypatch, None)

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is None
    assert "Not inside tmux" in why_not


def test_a_session_with_no_places_still_resolves(monkeypatch, tmp_path):
    """Sometimes there is no worktree at all, and killing the session is the ask."""
    (tmp_path / "elsewhere").mkdir()
    _panes(monkeypatch, notes=[tmp_path / "elsewhere"])
    _attached_to(monkeypatch, "notes")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.places == []


def test_a_named_key_resolves_the_session_sitting_in_it(monkeypatch, tmp_path):
    _managed(tmp_path, "wanted")
    _panes(monkeypatch, its_session=[tmp_path / "wanted"])
    _attached_to(monkeypatch, "somewhere-else")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "wanted")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "its_session"
    assert doomed.from_inside is False  # nothing to switch away from


def test_naming_a_key_acts_on_the_whole_session(monkeypatch, tmp_path):
    """The asymmetry that would otherwise strand places: name one, get the set."""
    _managed(tmp_path, "base", "on-top")
    _panes(monkeypatch, stacked=[tmp_path / "base", tmp_path / "on-top"])
    _attached_to(monkeypatch, "elsewhere")

    doomed, _ = target.resolve_toss_target(_config(_root(tmp_path)), "base")

    assert doomed is not None
    assert [p.key for p in doomed.places] == ["base", "on-top"]


def test_naming_the_session_you_are_in_still_switches_you_out(monkeypatch, tmp_path):
    _managed(tmp_path, "here")
    _panes(monkeypatch, here=[tmp_path / "here"])
    _attached_to(monkeypatch, "here")

    doomed, _ = target.resolve_toss_target(_config(_root(tmp_path)), "here")

    assert doomed is not None
    assert doomed.from_inside is True


def test_an_unknown_key_is_rejected(monkeypatch, tmp_path):
    _attached_to(monkeypatch, "mine")

    doomed, why_not = target.resolve_toss_target(_config(PlaceRoot(path=tmp_path)), "nope")

    assert doomed is None
    assert "No configured root has a directory" in why_not


def test_a_key_with_no_session_is_rejected(monkeypatch, tmp_path):
    """Releasing a directory with no session is `wt rm`, not this."""
    _managed(tmp_path, "idle")
    _panes(monkeypatch)
    _attached_to(monkeypatch, "mine")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "idle")

    assert doomed is None
    assert "No tmux session is in" in why_not


def test_a_protected_place_is_not_owned(monkeypatch, tmp_path):
    """Everyone passes through the trunk worktree; that isn't owning it.

    It can never be released, so listing it in every confirmation is a line you
    learn to skip past - which is how a real one gets missed.
    """
    _managed(tmp_path, "main", "scratch")
    _panes(monkeypatch, catchall=[tmp_path / "main", tmp_path / "scratch"])
    _attached_to(monkeypatch, "catchall")

    doomed, _ = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is not None
    assert [p.key for p in doomed.places] == ["scratch"]


def test_a_session_only_in_a_protected_place_owns_nothing(monkeypatch, tmp_path):
    """A session parked in main tears down as a plain session kill."""
    _managed(tmp_path, "main")
    _panes(monkeypatch, wanderer=[tmp_path / "main"])
    _attached_to(monkeypatch, "wanderer")

    doomed, _ = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is not None
    assert doomed.places == []


def test_protected_keys_are_configurable(tmp_path):
    root = PlaceRoot(path=tmp_path, protected=("trunk",))

    assert root.is_protected("trunk")
    assert not root.is_protected("main")


def test_a_protected_session_is_refused(monkeypatch, tmp_path):
    """A long-lived catchall isn't tied to one piece of work - closing it just loses windows."""
    _managed(tmp_path, "scratch")
    _panes(monkeypatch, main=[tmp_path / "scratch"])
    _attached_to(monkeypatch, "main")
    config = _config(_root(tmp_path))
    config.places.protected_sessions = ("main",)

    doomed, why_not = target.resolve_toss_target(config, None)

    assert doomed is None
    assert "protected" in why_not
    assert "protected_sessions" in why_not  # names the way to change it


def test_a_protected_session_is_refused_when_named_too(monkeypatch, tmp_path):
    """Naming a place must not be a way around the session guard."""
    _managed(tmp_path, "scratch")
    _panes(monkeypatch, main=[tmp_path / "scratch"])
    _attached_to(monkeypatch, "elsewhere")
    config = _config(_root(tmp_path))
    config.places.protected_sessions = ("main",)

    doomed, why_not = target.resolve_toss_target(config, "scratch")

    assert doomed is None
    assert "protected" in why_not


def test_sessions_are_unprotected_by_default(monkeypatch, tmp_path):
    _managed(tmp_path, "scratch")
    _panes(monkeypatch, main=[tmp_path / "scratch"])
    _attached_to(monkeypatch, "main")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None


def test_places_are_reported_in_key_order(monkeypatch, tmp_path):
    """The confirmation is read by a human; a stable order makes it scannable."""
    _managed(tmp_path, "zeta", "alpha")
    _panes(monkeypatch, work=[tmp_path / "zeta", tmp_path / "alpha"])
    _attached_to(monkeypatch, "work")

    doomed, _ = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is not None
    assert [p.key for p in doomed.places] == ["alpha", "zeta"]


def test_a_place_that_is_gone_is_still_part_of_the_set(monkeypatch, tmp_path):
    """Otherwise a session outliving its worktree could not be closed by this."""
    root = PlaceRoot(
        path=tmp_path, list=f"echo {tmp_path}/vanished", path_of=f"echo {tmp_path}/{{key}}"
    )
    _managed(tmp_path, "vanished")
    _panes(monkeypatch, ghost=[tmp_path / "vanished"])
    _attached_to(monkeypatch, "ghost")

    doomed, _ = target.resolve_toss_target(_config(root), None)

    assert doomed is not None
    assert [p.key for p in doomed.places] == ["vanished"]


def test_place_exists_reflects_the_directory(tmp_path):
    place = ownership.Place("k", PlaceRoot(path=tmp_path), tmp_path / "gone")

    assert place.exists is False
    (tmp_path / "gone").mkdir()
    assert place.exists is True
