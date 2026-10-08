"""Working out what `place toss` should tear down.

The unit is a place. A session closes with it only when it is dedicated to that
place; a session that holds other places is shared, and this release refuses it
rather than closing part of it.
"""

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.places import ownership, target, workspace_purpose


def _root(tmp_path: Path) -> PlaceRoot:
    return PlaceRoot(
        path=tmp_path,
        destroy="release {key}",
        list=f"find {tmp_path} -name .git -exec dirname {{}} \\;",
        path_of=f"echo {tmp_path}/{{key}}",
    )


def _managed(tmp_path: Path, *keys: str) -> None:
    for key in keys:
        (tmp_path / key / ".git").mkdir(parents=True)


def _panes(monkeypatch, *panes: tuple[str, str, Path | None]) -> None:
    """Panes as (session, window, path); pane IDs are made up in order."""
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1"})
    snapshot = [
        ownership.Pane(session, window, f"%{n}", path)
        for n, (session, window, path) in enumerate(panes, start=1)
    ]
    monkeypatch.setattr(
        target.session, "exists", lambda name: any(p.session == name for p in snapshot)
    )
    monkeypatch.setattr(target.ownership, "panes", lambda: snapshot)
    monkeypatch.setattr(target.ownership, "pane_snapshot", lambda: snapshot)


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
    assert [p.pane for p in doomed.session_windows["@2"]] == ["%2"]


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


def test_unnamed_toss_outside_every_place_closes_current_workspace(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@1", tmp_path))
    _attached_to(monkeypatch, "notes")
    monkeypatch.chdir(tmp_path)
    doomed, why_not = target.resolve_toss_target(_config(), None)
    assert why_not == ""
    assert doomed.session == "notes" and doomed.places == []


def test_current_workspace_without_a_listed_directory_closes(monkeypatch, tmp_path):
    _panes(monkeypatch, ("job", "@13", tmp_path))
    _attached_to(monkeypatch, "job")
    doomed, why_not = target.resolve_toss_target(_config(PlaceRoot(path=tmp_path)), None)
    assert why_not == ""
    assert doomed.session == "job" and doomed.places == []


def test_current_workspace_closes_all_its_windows(monkeypatch, tmp_path):
    _managed(tmp_path, "a")
    _panes(monkeypatch, ("work", "@1", tmp_path / "a"), ("work", "@2", tmp_path))
    _attached_to(monkeypatch, "work")
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)
    assert why_not == ""
    assert doomed.session == "work" and doomed.windows == ["@1", "@2"]
    assert [p.key for p in doomed.places] == ["a"]


def test_an_unattended_bare_toss_of_your_own_session_needs_the_key(monkeypatch, tmp_path):
    """A lemon tearing down the session it runs in should have to say so."""
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")
    monkeypatch.chdir(tmp_path / "feat")
    config = _config(_root(tmp_path))

    doomed, why_not = target.resolve_toss_target(config, None, unattended=True)
    assert doomed is None
    assert "session you are running in ('feat')" in why_not
    assert "place toss feat" in why_not

    doomed, why_not = target.resolve_toss_target(config, None, unattended=False)
    assert why_not == ""
    assert doomed is not None and doomed.session == "feat"


def test_an_unattended_bare_toss_with_an_unknown_caller_refuses_to_close_a_session(
    monkeypatch, tmp_path
):
    """No TMUX_PANE: the closing session may well be the caller's, so it is treated as such."""
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"))
    _attached_to(monkeypatch, None)
    monkeypatch.chdir(tmp_path / "feat")
    config = _config(_root(tmp_path))

    doomed, why_not = target.resolve_toss_target(config, None, unattended=True)
    assert doomed is None
    assert "can't be told (no TMUX_PANE)" in why_not
    assert "place toss feat" in why_not

    doomed, why_not = target.resolve_toss_target(config, None, unattended=False)
    assert why_not == "" and doomed is not None


def test_unattended_current_workspace_always_requires_a_name(monkeypatch, tmp_path):
    _managed(tmp_path, "feat", "other")
    _panes(monkeypatch, ("work", "@1", tmp_path / "feat"), ("work", "@2", tmp_path / "other"))
    _attached_to(monkeypatch, "work")
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None, unattended=True)
    assert doomed is None
    assert "place toss work" in why_not


def test_current_workspace_wins_over_the_callers_cwd(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("lemon", "@2", tmp_path))
    _attached_to(monkeypatch, "lemon")
    monkeypatch.chdir(tmp_path / "feat")
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)
    assert why_not == ""
    assert doomed.session == "lemon" and doomed.places == []


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


def test_a_named_key_resolves_the_session_dedicated_to_it(monkeypatch, tmp_path):
    _managed(tmp_path, "wanted")
    _panes(monkeypatch, ("its_session", "@5", tmp_path / "wanted"))
    _attached_to(monkeypatch, "somewhere-else")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "wanted")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "its_session"
    assert doomed.windows == ["@5"]


def test_a_shared_session_loses_only_its_windows_in_the_place(monkeypatch, tmp_path):
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

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == ""
    assert doomed.windows == []
    assert sorted(doomed.partial) == ["@4", "@7"]
    assert [p.pane for p in doomed.partial["@7"]] == ["%3"]
    assert doomed.closing == ["@4", "@7"]
    assert [p.key for p in doomed.places] == ["feat/merged"]


def test_current_workspace_can_release_multiple_exclusive_directories(monkeypatch, tmp_path):
    _managed(tmp_path, "base", "on-top")
    _panes(monkeypatch, ("base", "@1", tmp_path / "base"), ("base", "@2", tmp_path / "on-top"))
    _attached_to(monkeypatch, "base")
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)
    assert why_not == ""
    assert doomed.session == "base" and not doomed.partial
    assert [p.key for p in doomed.places] == ["base", "on-top"]


def test_an_unnamed_session_with_a_window_elsewhere_keeps_it(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("work", "@1", tmp_path / "feat"), ("work", "@2", Path.home()))
    _attached_to(monkeypatch, "work")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == ""
    assert list(doomed.partial) == ["@1"]


def test_named_workspace_can_span_directories_in_one_window(monkeypatch, tmp_path):
    _managed(tmp_path, "feat", "other")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@1", tmp_path / "other"))
    _attached_to(monkeypatch, "feat")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert why_not == ""
    assert doomed is not None and doomed.session == "feat"
    assert doomed.windows == ["@1"]
    assert {place.key for place in doomed.places} == {"feat", "other"}


def test_directory_key_still_refuses_a_mixed_window(monkeypatch, tmp_path):
    _managed(tmp_path, "feat", "other")
    _panes(monkeypatch, ("work", "@1", tmp_path / "feat"), ("work", "@1", tmp_path / "other"))
    _attached_to(monkeypatch, "work")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert doomed is None
    assert "Window @1" in why_not


def test_named_workspace_leaves_other_workspaces_and_shared_directory(monkeypatch, tmp_path):
    """A shell elsewhere that cd-ed in would otherwise sit in a deleted directory."""
    _managed(tmp_path, "feat")
    _panes(
        monkeypatch,
        ("feat", "@1", tmp_path / "feat"),
        ("other", "@8", tmp_path / "feat" / "docs"),
        ("other", "@9", Path.home()),
    )
    _attached_to(monkeypatch, "other")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "feat"
    assert doomed.windows == ["@1"]
    assert not doomed.partial and not doomed.places
    assert "used by another workspace" in doomed.kept[0]


def test_a_window_in_a_protected_session_is_left_open_and_reported(monkeypatch, tmp_path):
    """Hands off a protected session, even one window at a time."""
    _managed(tmp_path, "feat")
    _panes(
        monkeypatch,
        ("feat", "@1", tmp_path / "feat"),
        ("hq", "@8", tmp_path / "feat" / "docs"),
        ("hq", "@9", Path.home()),
    )
    _attached_to(monkeypatch, "hq")
    config = _config(_root(tmp_path))
    config.places.protected_sessions = ("hq",)

    doomed, why_not = target.resolve_toss_target(config, "feat")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "feat"
    assert doomed.partial == {}
    assert not doomed.places
    assert "used by another workspace" in doomed.kept[0]


def test_named_workspace_closes_only_the_selected_session(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("twin", "@2", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "feat")

    assert why_not == ""
    assert doomed.session == "feat" and doomed.windows == ["@1"]
    assert not doomed.places


def test_an_unknown_key_is_rejected(monkeypatch, tmp_path):
    _attached_to(monkeypatch, "mine")

    doomed, why_not = target.resolve_toss_target(_config(PlaceRoot(path=tmp_path)), "nope")

    assert doomed is None
    assert "No configured root has a directory" in why_not


def test_named_session_without_a_place_resolves(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", tmp_path), ("notes", "@4", tmp_path))
    monkeypatch.setattr(target.session, "exists", lambda name: True)

    doomed, why_not = target.resolve_toss_target(_config(), "notes")

    assert why_not == ""
    assert doomed is not None
    assert doomed.session == "notes"
    assert doomed.place is None
    assert doomed.places == []
    assert doomed.windows == ["@3", "@4"]


def test_workspace_can_release_its_same_named_directory(monkeypatch, tmp_path):
    _managed(tmp_path, "notes")
    _panes(monkeypatch, ("notes", "@3", tmp_path / "notes"))

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "notes")

    assert why_not == ""
    assert doomed is not None and doomed.place is not None
    assert doomed.places[0].key == "notes"


def test_workspace_can_release_its_list_only_directory(monkeypatch, tmp_path):
    _managed(tmp_path, "notes")
    _panes(monkeypatch, ("notes", "@3", tmp_path / "notes"))
    root = PlaceRoot(path=tmp_path, list=f"echo {tmp_path}/notes", destroy="release {key}")

    doomed, why_not = target.resolve_toss_target(_config(root), "notes")

    assert why_not == ""
    assert doomed is not None and doomed.place is not None
    assert doomed.places[0].key == "notes"


def test_failed_directory_discovery_still_closes_named_workspace(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", tmp_path))
    doomed, why_not = target.resolve_toss_target(
        _config(PlaceRoot(path=tmp_path, list="false")), "notes"
    )
    assert why_not == ""
    assert doomed.session == "notes" and doomed.places == []
    assert "Directory discovery failed" in doomed.kept[0]


def test_failed_directory_lookup_still_closes_named_workspace(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", tmp_path))
    doomed, why_not = target.resolve_toss_target(
        _config(PlaceRoot(path=tmp_path, path_of="false")), "notes"
    )
    assert why_not == ""
    assert doomed.session == "notes" and doomed.places == []
    assert "Directory lookup failed" in doomed.kept[0]


def test_synthesized_missing_place_does_not_shadow_session(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", tmp_path))
    monkeypatch.setattr(target.session, "exists", lambda name: True)

    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "notes")

    assert why_not == ""
    assert doomed is not None and doomed.place is None


def test_named_workspace_releases_its_exclusive_directory(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("notes", "@3", tmp_path / "feat"))
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "notes")
    assert why_not == ""
    assert doomed.session == "notes"
    assert [p.key for p in doomed.places] == ["feat"]


def test_session_only_toss_refuses_a_failed_pane_query(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", tmp_path))
    monkeypatch.setattr(target.session, "exists", lambda name: True)
    monkeypatch.setattr(target.ownership, "pane_snapshot", lambda: None)

    doomed, why_not = target.resolve_toss_target(_config(), "notes")

    assert doomed is None
    assert "Could not inspect panes" in why_not


def test_named_workspace_with_unknown_pane_directory_closes_without_cleanup(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", None))
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: set())
    doomed, why_not = target.resolve_toss_target(_config(), "notes")
    assert why_not == ""
    assert doomed.session == "notes" and doomed.places == []


def test_unknown_live_lemon_directory_refuses_workspace(monkeypatch, tmp_path):
    _panes(monkeypatch, ("notes", "@3", None))
    doomed, why_not = target.resolve_toss_target(_config(), "notes")
    assert doomed is None
    assert "Could not identify a lemon's place" in why_not


def test_protected_bare_session_is_refused(monkeypatch, tmp_path):
    _panes(monkeypatch, ("hq", "@3", tmp_path))
    config = _config()
    config.places.protected_sessions = ("hq",)

    doomed, why_not = target.resolve_toss_target(config, "hq")

    assert doomed is None
    assert "protected" in why_not


def test_session_only_plan_detects_new_window(monkeypatch, tmp_path):
    monkeypatch.setattr(target.session, "exists", lambda name: True)
    _panes(monkeypatch, ("notes", "@3", tmp_path))
    config = _config()
    planned, _ = target.resolve_toss_target(config, "notes")
    assert planned is not None
    _panes(monkeypatch, ("notes", "@3", tmp_path), ("notes", "@4", tmp_path))

    assert "windows @4 appeared" in target.changed_since(config, "notes", planned)


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


def test_directory_protection_does_not_implicitly_protect_a_workspace(monkeypatch, tmp_path):
    _managed(tmp_path, "main")
    _panes(monkeypatch, ("main", "@1", tmp_path / "main"))
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), "main")
    assert why_not == ""
    assert doomed.session == "main" and doomed.places == []
    assert "protected directory" in doomed.kept[0]


def test_protected_directory_stays_when_unprotected_workspace_closes(monkeypatch, tmp_path):
    _managed(tmp_path, "main")
    _panes(monkeypatch, ("job", "@1", tmp_path / "main"))
    _attached_to(monkeypatch, "job")
    doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path)), None)
    assert why_not == ""
    assert doomed.session == "job" and doomed.places == []
    assert "protected directory" in doomed.kept[0]


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
        path=tmp_path,
        list=f"echo {tmp_path}/vanished",
        path_of=f"echo {tmp_path}/{{key}}",
        destroy="release {key}",
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


def test_an_unchanged_plan_passes_the_recheck(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")
    config = _config(_root(tmp_path))
    planned, _ = target.resolve_toss_target(config, "feat")

    assert planned is not None
    assert target.changed_since(config, "feat", planned) == ""


def test_a_window_opened_in_the_place_since_fails_the_recheck(monkeypatch, tmp_path):
    """New work in the place that the confirmation never showed."""
    _managed(tmp_path, "feat", "other")
    _panes(monkeypatch, ("work", "@1", tmp_path / "feat"), ("work", "@2", tmp_path / "other"))
    _attached_to(monkeypatch, "work")
    config = _config(_root(tmp_path))
    planned, _ = target.resolve_toss_target(config, "feat")
    assert planned is not None

    _panes(
        monkeypatch,
        ("work", "@1", tmp_path / "feat"),
        ("work", "@2", tmp_path / "other"),
        ("work", "@3", tmp_path / "feat" / "src"),
    )

    why = target.changed_since(config, "feat", planned)

    assert "windows @3 appeared" in why
    assert "nothing was closed" in why


def test_a_dedicated_session_that_gained_a_window_fails_the_recheck(monkeypatch, tmp_path):
    """The whole session is about to die; a window it grew meanwhile was never confirmed."""
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")
    config = _config(_root(tmp_path))
    planned, _ = target.resolve_toss_target(config, "feat")
    assert planned is not None

    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@5", Path.home()))

    assert "windows @5 appeared" in target.changed_since(config, "feat", planned)


def test_a_pane_split_in_a_closing_window_fails_the_recheck(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")
    config = _config(_root(tmp_path))
    planned, _ = target.resolve_toss_target(config, "feat")
    assert planned is not None

    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@1", tmp_path / "feat"))

    assert "a pane moved or was added" in target.changed_since(config, "feat", planned)


def test_a_plan_that_now_refuses_fails_the_recheck_with_the_reason(monkeypatch, tmp_path):
    _managed(tmp_path, "feat", "other")
    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"))
    _attached_to(monkeypatch, "feat")
    config = _config(_root(tmp_path))
    planned, _ = target.resolve_toss_target(config, "feat")
    assert planned is not None

    _panes(monkeypatch, ("feat", "@1", tmp_path / "feat"), ("feat", "@1", tmp_path / "other"))

    why = target.changed_since(config, "feat", planned)

    assert "a pane moved or was added" in why
    assert "nothing was closed" in why


def test_the_recheck_sees_a_split_on_a_real_tmux_server(monkeypatch, tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-recheck-test-{uuid.uuid4().hex[:8]}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    _managed(tmp_path, "merged", "live")
    started = tmux(
        "-f", "/dev/null", "new-session", "-d", "-s", "katamari", "-c", str(tmp_path / "live")
    )
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    tmux("new-window", "-d", "-t", "katamari", "-c", str(tmp_path / "merged"))
    socket = tmux("display-message", "-p", "-t", "katamari", "#{socket_path}").stdout.strip()
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    monkeypatch.delenv("TMUX_PANE", raising=False)
    config = _config(_root(tmp_path))
    try:
        planned, why_not = target.resolve_toss_target(config, "merged")
        assert why_not == ""
        assert planned is not None
        (window,) = planned.partial
        assert target.changed_since(config, "merged", planned) == ""

        tmux("split-window", "-d", "-t", window, "-c", str(tmp_path / "live"))

        why = target.changed_since(config, "merged", planned)

        assert f"Window {window}" in why  # the split pane made it a mixed window
        assert "nothing was closed" in why
    finally:
        tmux("kill-server")


def _server(monkeypatch, name: str, windows: list[tuple[str, Path]]):
    """A private tmux server with the given (session, cwd) windows; returns a runner."""

    def tmux(*args):
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    first_session, first_cwd = windows[0]
    started = tmux(
        "-f", "/dev/null", "new-session", "-d", "-s", first_session, "-c", str(first_cwd)
    )
    if started.returncode != 0:
        pytest.skip(f"cannot start tmux: {started.stderr.strip()}")

    for session, cwd in windows[1:]:
        if tmux("has-session", "-t", f"={session}").returncode == 0:
            tmux("new-window", "-d", "-t", f"={session}", "-c", str(cwd))
        else:
            tmux("new-session", "-d", "-s", session, "-c", str(cwd))
    socket = tmux("display-message", "-p", "-t", first_session, "#{socket_path}").stdout.strip()
    pane = tmux("display-message", "-p", "-t", first_session, "#{pane_id}").stdout.strip()
    monkeypatch.setenv("TMUX", f"{socket},0,0")
    monkeypatch.setenv("TMUX_PANE", pane)  # the caller sits in the first session, for real
    return tmux


def test_bare_toss_under_an_unlisted_root_refuses_on_a_real_server(monkeypatch, tmp_path):
    """The trial incident, replayed: the caller's session must still be there afterward."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    cwd = tmp_path / "brief" / "approve-status"
    cwd.mkdir(parents=True)
    tmux = _server(monkeypatch, f"lemonaid-bare-{uuid.uuid4().hex[:8]}", [("play-lemonaid", cwd)])
    monkeypatch.chdir(cwd)
    try:
        doomed, why_not = target.resolve_toss_target(
            _config(PlaceRoot(path=tmp_path)), None, unattended=True
        )

        assert doomed is None
        assert "An unattended toss has to name it" in why_not
        assert tmux("has-session", "-t", "=play-lemonaid").returncode == 0
    finally:
        tmux("kill-server")


def test_interactive_bare_toss_outside_every_root_selects_current_workspace(monkeypatch, tmp_path):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    _managed(tmp_path / "root", "feat")
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    tmux = _server(monkeypatch, f"lemonaid-bare-{uuid.uuid4().hex[:8]}", [("notes", cwd)])
    monkeypatch.chdir(cwd)
    try:
        doomed, why_not = target.resolve_toss_target(_config(_root(tmp_path / "root")), None)

        assert why_not == ""
        assert doomed is not None and doomed.session == "notes"
        assert doomed.places == []
        assert doomed.windows
        assert tmux("has-session", "-t", "=notes").returncode == 0
    finally:
        tmux("kill-server")


def test_unattended_bare_toss_of_own_dedicated_session_refuses_on_a_real_server(
    monkeypatch, tmp_path
):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    _managed(tmp_path, "feat")
    tmux = _server(
        monkeypatch, f"lemonaid-bare-{uuid.uuid4().hex[:8]}", [("feat", tmp_path / "feat")]
    )
    monkeypatch.chdir(tmp_path / "feat")
    config = _config(_root(tmp_path))
    try:
        doomed, why_not = target.resolve_toss_target(config, None, unattended=True)
        assert doomed is None
        assert "session you are running in" in why_not

        doomed, why_not = target.resolve_toss_target(config, "feat", unattended=True)
        assert why_not == ""
        assert doomed is not None and doomed.session == "feat"
        assert tmux("has-session", "-t", "=feat").returncode == 0
    finally:
        tmux("kill-server")
