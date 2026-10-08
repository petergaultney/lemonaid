from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.places import ownership, target, workspace_purpose


def _setup(monkeypatch, tmp_path, paths, protected=()):
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1"})
    root = PlaceRoot(path=tmp_path, destroy="release {key}")
    places = [
        ownership.Place(key, root, tmp_path / key) for key in ("feat", "outer", "outer/inner")
    ]
    for place in places:
        place.directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ownership, "managed_places_checked", lambda cfg: list(places))
    monkeypatch.setattr(target.session, "exists", lambda name: name in {p[0] for p in paths})
    monkeypatch.setattr(
        ownership,
        "pane_snapshot",
        lambda: [
            ownership.Pane(name, f"@{i}", f"%{i}", path) for i, (name, path) in enumerate(paths, 1)
        ],
    )
    monkeypatch.setattr(ownership, "panes", lambda: ownership.pane_snapshot())
    return Config(places=PlacesConfig(roots=[root], protected_sessions=protected))


def test_workspace_name_wins_even_when_same_directory_is_shared(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("feat", tmp_path / "feat"), ("survivor", tmp_path / "feat")]
    )
    doomed, why = target.resolve_toss_target(cfg, "feat")
    assert not why
    assert doomed.session == "feat" and doomed.windows == ["@1"]
    assert doomed.places == [] and not doomed.partial
    assert "used by another workspace" in doomed.kept[0]


def test_named_workspace_keeps_directory_containing_idle_child(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("job", tmp_path / "outer")])
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert not why
    assert doomed.session == "job" and doomed.places == []
    assert "contains another managed directory" in doomed.kept[0]


def test_unknown_survivor_path_prevents_directory_release(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("job", tmp_path / "feat"), ("survivor", None)])
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert not why
    assert doomed.session == "job" and doomed.places == []
    assert "directory is unknown" in doomed.kept[0]


def test_session_protection_precedes_failed_directory_discovery(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("HQ", tmp_path)], protected=("HQ",))
    monkeypatch.setattr(ownership, "managed_places_checked", lambda cfg: None)
    doomed, why = target.resolve_toss_target(cfg, "HQ")
    assert doomed is None and "protected" in why


def test_session_named_for_directory_can_clean_up_after_cd(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("feat", tmp_path)])
    doomed, why = target.resolve_toss_target(cfg, "feat")
    assert not why
    assert doomed.session == "feat"
    assert [p.key for p in doomed.places] == ["feat"]


def test_new_surviving_user_aborts_a_previously_confirmed_cleanup(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("job", tmp_path / "feat")])
    planned, _ = target.resolve_toss_target(cfg, "job")
    _setup(monkeypatch, tmp_path, [("job", tmp_path / "feat"), ("survivor", tmp_path / "feat")])
    assert "nothing was closed" in target.changed_since(cfg, "job", planned)


def test_hybrid_lemons_refuse_even_without_configured_places(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("hq", tmp_path / "a"), ("hq", tmp_path / "b")])
    monkeypatch.setattr(ownership, "managed_places_checked", lambda cfg: [])
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    doomed, why = target.resolve_toss_target(cfg, "hq", unattended=True)
    assert doomed is None
    assert "hybrid" in why and "not a managed place" in why


def test_author_and_reviewer_in_subdirectories_share_one_place(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "feat"), ("job", tmp_path / "feat/tests")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert not why and doomed.session == "job"
    assert [p.key for p in doomed.places] == ["feat"]


def test_no_lemons_and_mixed_places_closes_without_directory_cleanup(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "feat"), ("job", tmp_path / "outer/inner")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: set())
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert not why and doomed.session == "job"
    assert doomed.places == []
    assert "not consistent" in doomed.kept[0]


def test_no_lemons_and_consistent_place_releases_directory(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "feat"), ("job", tmp_path / "feat/tests")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: set())
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert not why and [p.key for p in doomed.places] == ["feat"]


def test_failed_process_inspection_refuses_workspace(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("job", tmp_path / "feat")])
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: None)
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert doomed is None and "Could not inspect lemons" in why


def test_new_hybrid_lemon_aborts_confirmed_toss(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "feat"), ("job", tmp_path / "outer/inner")]
    )
    planned, _ = target.resolve_toss_target(cfg, "job")
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    assert "nothing was closed" in target.changed_since(cfg, "job", planned)


def test_failed_discovery_does_not_allow_hybrid_session(monkeypatch, tmp_path):
    cfg = _setup(monkeypatch, tmp_path, [("hq", tmp_path / "a"), ("hq", tmp_path / "b")])
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    monkeypatch.setattr(ownership, "managed_places_checked", lambda cfg: None)
    doomed, why = target.resolve_toss_target(cfg, "hq")
    assert doomed is None and "not a managed place" in why


def test_directory_key_cannot_close_windows_in_hybrid_workspace(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("hq", tmp_path / "feat"), ("hq", tmp_path / "outer/inner")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    doomed, why = target.resolve_toss_target(cfg, "feat")
    assert doomed is None and "not a managed place" in why


def test_nested_managed_places_remain_distinct_purposes(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "outer"), ("job", tmp_path / "outer/inner")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert doomed is None and "hybrid" in why


def test_failed_discovery_never_collapses_nested_lemon_places(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "outer"), ("job", tmp_path / "outer/inner")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    monkeypatch.setattr(ownership, "managed_places_checked", lambda cfg: None)
    doomed, why = target.resolve_toss_target(cfg, "job", unattended=True)
    assert doomed is None and "not a managed place" in why


def test_unknown_nested_paths_need_successful_place_discovery(monkeypatch, tmp_path):
    cfg = _setup(
        monkeypatch, tmp_path, [("job", tmp_path / "unknown"), ("job", tmp_path / "unknown/tests")]
    )
    monkeypatch.setattr(workspace_purpose, "lemon_panes", lambda name: {"%1", "%2"})
    monkeypatch.setattr(ownership, "managed_places_checked", lambda cfg: [])
    doomed, why = target.resolve_toss_target(cfg, "job")
    assert doomed is None and "not a managed place" in why
