"""Working out what `place toss` should tear down.

The unit is a place. A session closes with it only when it is dedicated to that
place; a session that holds other places is shared, and this release refuses it
rather than closing part of it.
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


def _panes(monkeypatch, *panes: tuple[str, str, Path | None]) -> None:
    """Panes as (session, window, path); pane IDs are made up in order."""
    snapshot = [
        ownership.Pane(session, window, f"%{n}", path)
        for n, (session, window, path) in enumerate(panes, start=1)
    ]
    monkeypatch.setattr(target.ownership, "panes", lambda: snapshot)


def _attached_to(monkeypatch, session: str | None) -> None:
    monkeypatch.setattr(
        target.tmux.navigation,
        "get_current_location",
        lambda: (session, "%1" if session else None),
    )


def _config(*roots: PlaceRoot) -> Config:
    return Config(places=PlacesConfig(roots=list(roots)))


def test_unnamed_toss_is_the_place_you_are_standing_in(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@2", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")
    monkeypatch.chdir(tmp_path / "feat")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "feat"
    assert [p.key for p in doomed.places] == ["feat"]
    assert doomed.place is not None and doomed.place.key == "feat"
    assert doomed.windows == ["@1", "@2"]


def test_unnamed_toss_from_deep_inside_the_place(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    (tmp_path / "feat" / "src" / "pkg").mkdir(parents=True)
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat" / "src" / "pkg"))
    _attached_to(monkeypatch, "feat")
    monkeypatch.chdir(tmp_path / "feat" / "src" / "pkg")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "feat"


def test_unnamed_toss_outside_tmux_needs_a_place(monkeypatch, tmp_path):
    _attached_to(monkeypatch, None)
    _panes(monkeypatch)
    monkeypatch.chdir(tmp_path)

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is None
    assert "Name a place" in why_not


def test_unnamed_toss_outside_tmux_in_a_place_releases_it(monkeypatch, tmp_path):
    """A shell with no tmux is still standing somewhere; that somewhere is the target."""
    _managed(tmp_path, "idle")
    _attached_to(monkeypatch, None)
    _panes(monkeypatch)
    monkeypatch.chdir(tmp_path / "idle")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == ""
    assert [p.key for p in doomed.places] == ["idle"]


def test_a_session_with_no_places_still_resolves(monkeypatch, tmp_path):
    """Sometimes there is no worktree at all, and killing the session is the ask."""
    (tmp_path / "elsewhere").mkdir()
    _panes(monkeypatch, ("notes", "@1", tmp_path / "elsewhere"), ("notes", "@2", Path.home()))
    _attached_to(monkeypatch, "notes")
    monkeypatch.chdir(tmp_path / "elsewhere")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "notes"
    assert doomed.places == []
    assert doomed.place is None
    assert doomed.windows == ["@1", "@2"]


def test_unnamed_toss_outside_a_place_in_a_session_holding_places_is_refused(monkeypatch, tmp_path):
    """The directory did not say which place; the session holds two. Don't guess."""
    _managed(tmp_path, "a", "b")
    (tmp_path / "elsewhere").mkdir()
    _panes(
        monkeypatch,
        ("work", "@1", tmp_path / "a"),
        ("work", "@2", tmp_path / "b"),
        ("work", "@3", tmp_path / "elsewhere"),
    )
    _attached_to(monkeypatch, "work")
    monkeypatch.chdir(tmp_path / "elsewhere")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is None
    assert "'a', 'b'" in why_not
    assert "place toss <key>" in why_not


def test_a_named_key_resolves_the_session_dedicated_to_it(monkeypatch, tmp_path):
    _managed(tmp_path, "wanted")
    _panes(monkeypatch, ("its_session", "@5", tmp_path / "wanted"))
    _attached_to(monkeypatch, "somewhere-else")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "wanted")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "its_session"
    assert doomed.windows == ["@5"]


def test_a_shared_session_is_refused_naming_the_windows(monkeypatch, tmp_path):
    """The case this exists for: tossing one merged worktree must not take the others."""
    _managed(tmp_path, "feat/merged", "feat/live")
    _panes(
        monkeypatch,
        ("katamari", "@1", tmp_path / "feat/live"),
        ("katamari", "@4", tmp_path / "feat/merged"),
        ("katamari", "@7", tmp_path / "feat/merged" / "src"),
    )
    _attached_to(monkeypatch, "katamari")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat/merged")

    assert doomed is None
    assert "'katamari' also holds 'feat/live'" in why_not
    assert "@4, @7" in why_not
    assert "place toss feat/merged" in why_not


def test_a_named_session_that_grew_another_place_is_refused(monkeypatch, tmp_path):
    _managed(tmp_path, "base", "on-top")
    _panes(monkeypatch, ("base", "@1", tmp_path / "base"), ("base", "@2", tmp_path / "on-top"))
    _attached_to(monkeypatch, "base")
    monkeypatch.chdir(tmp_path / "base")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is None
    assert "'on-top'" in why_not


def test_an_unnamed_session_with_a_window_elsewhere_is_refused(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("work", "@1", tmp_path / "feat"), ("work", "@2", Path.home()))
    _attached_to(monkeypatch, "work")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert doomed is None
    assert "windows outside 'feat'" in why_not
    assert "@1" in why_not


def test_a_mixed_window_is_refused(monkeypatch, tmp_path):
    _managed(tmp_path, "feat", "other")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@1", tmp_path / "other"))
    _attached_to(monkeypatch, "feat")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert doomed is None
    assert "Window @1" in why_not


def test_an_onlooker_window_elsewhere_is_left_open_and_reported(monkeypatch, tmp_path):
    """A shell in another session that cd-ed in is not a reason to stop; it is told about."""
    _managed(tmp_path, "feat")
    _panes(
        monkeypatch,
        ("feat", "@1", tmp_path / "feat"),
        ("hq", "@8", tmp_path / "feat" / "docs"),
        ("hq", "@9", Path.home()),
    )
    _attached_to(monkeypatch, "hq")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "feat"
    assert doomed.left_open == ["hq:@8"]


def test_two_sessions_each_dedicated_is_refused(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("twin", "@2", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert doomed is None
    assert "2 sessions" in why_not
    assert "'feat'" in why_not and "'twin'" in why_not


def test_an_unknown_key_is_rejected(monkeypatch, tmp_path):
    _attached_to(monkeypatch, "mine")

    doomed, why_not = target.resolve_toss_target(_config(PlaceRoot(path=tmp_path)), "nope")

    assert doomed is None
    assert "No configured root has a directory" in why_not


def test_a_key_with_no_session_releases_just_that_place(monkeypatch, tmp_path):
    """An acquired directory nobody opened is exactly what would be left behind."""
    _managed(tmp_path, "idle", "unrelated")
    _panes(monkeypatch, ("mine", "@1", tmp_path / "unrelated"))
    _attached_to(monkeypatch, "mine")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "idle")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == ""
    assert [place.key for place in doomed.places] == ["idle"]
    assert doomed.windows == []


def test_a_place_only_a_hook_knows_about_is_planned_like_any_other(monkeypatch, tmp_path):
    """A root with `path_of` but no `list`: the named place is not in the listing."""
    (tmp_path / "quiet").mkdir()
    root = PlaceRoot(path=tmp_path, path_of=f"echo {tmp_path}/{{key}}")
    _panes(monkeypatch, ("quiet", "@1", tmp_path / "quiet"))
    _attached_to(monkeypatch, "elsewhere")

    doomed, why_not = target.resolve_toss_target(_config(root), "quiet")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "quiet"


def test_a_protected_place_is_refused(monkeypatch, tmp_path):
    _managed(tmp_path, "main")
    _panes(monkeypatch, ("main", "@1", tmp_path / "main"))
    _attached_to(monkeypatch, "mine")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "main")

    assert doomed is None
    assert "protected" in why_not


def test_standing_in_a_protected_place_is_refused(monkeypatch, tmp_path):
    """Bare toss from the trunk worktree names it, and it must not be released."""
    _managed(tmp_path, "main")
    _panes(monkeypatch, ("hq", "@1", tmp_path / "main"))
    _attached_to(monkeypatch, "hq")
    monkeypatch.chdir(tmp_path / "main")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is None
    assert "'main' is protected" in why_not


def test_a_window_in_a_protected_place_goes_with_a_dedicated_session(monkeypatch, tmp_path):
    """Everyone passes through the trunk worktree; that isn't holding another place."""
    _managed(tmp_path, "feat", "main")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@2", tmp_path / "main"))
    _attached_to(monkeypatch, "feat")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert why_not == ""
    assert doomed is not None
    assert [p.key for p in doomed.places] == ["feat"]
    assert doomed.windows == ["@1", "@2"]


def test_a_place_containing_another_managed_place_is_refused(monkeypatch, tmp_path):
    """The destroy hook is opaque; releasing the outer directory may take the inner one."""
    _managed(tmp_path, "outer", "outer/inner")
    _panes(monkeypatch, ("inner", "@1", tmp_path / "outer" / "inner"))
    _attached_to(monkeypatch, "elsewhere")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "outer")

    assert doomed is None
    assert "'outer' contains 'outer/inner'" in why_not


def test_a_place_containing_an_idle_managed_place_is_refused_too(monkeypatch, tmp_path):
    _managed(tmp_path, "outer", "outer/inner")
    _panes(monkeypatch)
    _attached_to(monkeypatch, None)
    monkeypatch.chdir(tmp_path / "outer")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)

    assert doomed is None
    assert "Toss those first" in why_not


def test_the_inner_of_nested_places_tosses_normally(monkeypatch, tmp_path):
    _managed(tmp_path, "outer", "outer/inner")
    _panes(monkeypatch, ("inner", "@1", tmp_path / "outer" / "inner"))
    _attached_to(monkeypatch, "elsewhere")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "outer/inner")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "inner"


def test_protected_keys_are_configurable(tmp_path):
    root = PlaceRoot(path=tmp_path, protected=("trunk",))

    assert root.is_protected("trunk")
    assert not root.is_protected("main")


def test_a_protected_session_is_refused(monkeypatch, tmp_path):
    """A long-lived catchall isn't tied to one piece of work - closing it just loses windows."""
    _managed(tmp_path, "scratch")
    _panes(monkeypatch, ("main", "@1", tmp_path / "scratch"))
    _attached_to(monkeypatch, "main")
    monkeypatch.chdir(tmp_path / "scratch")
    config = _config(_root(tmp_path))
    config.places.protected_sessions = ("main",)

    doomed, why_not = target.resolve_toss_target(config, None)

    assert doomed is None
    assert "protected" in why_not
    assert "protected_sessions" in why_not  # names the way to change it


def test_a_protected_session_is_refused_when_named_too(monkeypatch, tmp_path):
    """Naming a place must not be a way around the session guard."""
    _managed(tmp_path, "scratch")
    _panes(monkeypatch, ("main", "@1", tmp_path / "scratch"))
    _attached_to(monkeypatch, "elsewhere")
    config = _config(_root(tmp_path))
    config.places.protected_sessions = ("main",)

    doomed, why_not = target.resolve_toss_target(config, "scratch")

    assert doomed is None
    assert "protected" in why_not


def test_a_protected_session_holding_nothing_is_refused_from_inside(monkeypatch, tmp_path):
    _panes(monkeypatch, ("main", "@1", Path.home()))
    _attached_to(monkeypatch, "main")
    monkeypatch.chdir(tmp_path)
    config = _config(_root(tmp_path))
    config.places.protected_sessions = ("main",)

    doomed, why_not = target.resolve_toss_target(config, None)

    assert doomed is None
    assert "protected" in why_not


def test_sessions_are_unprotected_by_default(monkeypatch, tmp_path):
    _managed(tmp_path, "scratch")
    _panes(monkeypatch, ("main", "@1", tmp_path / "scratch"))
    _attached_to(monkeypatch, "main")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "scratch")

    assert why_not == ""
    assert doomed is not None


def test_a_place_that_is_gone_still_resolves(monkeypatch, tmp_path):
    """Otherwise a session outliving its worktree could not be closed by this."""
    root = PlaceRoot(
        path=tmp_path, list=f"echo {tmp_path}/vanished", path_of=f"echo {tmp_path}/{{key}}"
    )
    _managed(tmp_path, "vanished")
    _panes(monkeypatch, ("ghost", "@1", tmp_path / "vanished"))
    _attached_to(monkeypatch, "ghost")
    monkeypatch.chdir(tmp_path / "vanished")

    doomed, _ = target.resolve_toss_target(_config(root), None)

    assert doomed is not None
    assert [p.key for p in doomed.places] == ["vanished"]
    assert doomed.session == "ghost"


def test_place_exists_reflects_the_directory(tmp_path):
    place = ownership.Place("k", PlaceRoot(path=tmp_path), tmp_path / "gone")

    assert place.exists is False
    (tmp_path / "gone").mkdir()
    assert place.exists is True
