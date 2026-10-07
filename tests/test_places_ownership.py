"""Which places a session occupies, derived from tmux rather than recorded.

Nothing is written down when a place is opened, so a directory acquired by hand,
by `place open`, or by an agent all resolve the same way afterward.
"""

from pathlib import Path
from subprocess import CompletedProcess

from lemonaid.config import Config, PlaceRoot, PlacesConfig
from lemonaid.places import ownership


def _root(tmp_path: Path) -> PlaceRoot:
    """A root whose managed directories are the ones holding a .git."""
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
        ownership, "pane_paths", lambda: {k: list(v) for k, v in by_session.items()}
    )


def _config(*roots: PlaceRoot) -> Config:
    return Config(places=PlacesConfig(roots=list(roots)))


def test_panes_excludes_follow_mode_panes(monkeypatch):
    monkeypatch.setattr(
        ownership.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args[0],
            0,
            "work\t@1\t%1\t/work/feature\t\tpython\n"
            "work\t@1\t%2\t/work/scratch-origin\t1\tpython\n"
            "work\t@2\t%3\t/work/placeholder-origin\t\tenv LEMONAID_PLACEHOLDER=1 sleep 2147483647\n",
            "",
        ),
    )

    assert ownership.panes() == [ownership.Pane("work", "@1", "%1", Path("/work/feature"))]


def test_a_pane_without_a_path_is_kept_but_has_none(monkeypatch):
    monkeypatch.setattr(
        ownership.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "work\t@1\t%1\t\t\tsh\n", ""),
    )

    assert ownership.panes() == [ownership.Pane("work", "@1", "%1", None)]
    assert ownership.pane_paths() == {}


def test_a_session_owns_the_place_its_pane_sits_in(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, work=[tmp_path / "feat"])

    places = ownership.places_of("work", _config(_root(tmp_path)))

    assert [p.key for p in places] == ["feat"]


def test_a_root_listing_skips_a_directory_outside_the_root(monkeypatch, tmp_path):
    root_dir = tmp_path / "root"
    inside = root_dir / "inside"
    outside = tmp_path / "scratch" / "outside"
    inside.mkdir(parents=True)
    outside.mkdir(parents=True)
    root = PlaceRoot(path=root_dir, list="unused")
    monkeypatch.setattr(
        ownership.hooks, "list_directories_checked", lambda _root: [inside, outside]
    )

    places = ownership.managed_places(_config(root))

    assert [(place.key, place.directory) for place in places] == [("inside", inside)]


def test_a_pane_deep_inside_claims_the_place(monkeypatch, tmp_path):
    """A pane's directory is what it is for right now, wherever in the tree it sits."""
    _managed(tmp_path, "feat")
    (tmp_path / "feat" / "libs" / "thing").mkdir(parents=True)
    _panes(monkeypatch, work=[tmp_path / "feat" / "libs" / "thing"])

    assert [p.key for p in ownership.places_of("work", _config(_root(tmp_path)))] == ["feat"]


def test_place_at_picks_the_most_specific_place(tmp_path):
    _managed(tmp_path, "outer", "outer/inner")
    places = ownership.managed_places(_config(_root(tmp_path)))

    found = ownership.place_at(tmp_path / "outer" / "inner" / "src", places)

    assert found is not None
    assert found.key == "outer/inner"


def test_place_at_includes_protected_places(tmp_path):
    """Whether to act on one is the caller's decision; where a pane is, is not."""
    _managed(tmp_path, "main")
    places = ownership.managed_places(_config(_root(tmp_path)))

    found = ownership.place_at(tmp_path / "main", places)

    assert found is not None
    assert found.key == "main"


def test_place_at_is_none_outside_every_place(tmp_path):
    _managed(tmp_path, "feat")
    (tmp_path / "elsewhere").mkdir()

    assert (
        ownership.place_at(
            tmp_path / "elsewhere", ownership.managed_places(_config(_root(tmp_path)))
        )
        is None
    )


def test_place_at_resolves_symlinks(tmp_path):
    _managed(tmp_path, "feat")
    (tmp_path / "link").symlink_to(tmp_path / "feat")

    found = ownership.place_at(
        tmp_path / "link" / "sub", ownership.managed_places(_config(_root(tmp_path)))
    )

    assert found is not None
    assert found.key == "feat"


def test_several_panes_in_one_place_report_it_once(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, work=[tmp_path / "feat", tmp_path / "feat" / "sub", tmp_path / "feat"])

    assert [p.key for p in ownership.places_of("work", _config(_root(tmp_path)))] == ["feat"]


def test_a_session_can_own_several_places(monkeypatch, tmp_path):
    """Stacked PRs, or a catchall session that wandered."""
    _managed(tmp_path, "base", "on-top")
    _panes(monkeypatch, stacked=[tmp_path / "base", tmp_path / "on-top"])

    places = ownership.places_of("stacked", _config(_root(tmp_path)))

    assert [p.key for p in places] == ["base", "on-top"]


def test_a_session_with_no_managed_place_owns_nothing(monkeypatch, tmp_path):
    """Not an error - killing such a session is a legitimate thing to ask for."""
    _managed(tmp_path, "feat")
    (tmp_path / "elsewhere").mkdir()
    _panes(monkeypatch, notes=[tmp_path / "elsewhere"])

    assert ownership.places_of("notes", _config(_root(tmp_path))) == []


def test_only_this_sessions_panes_count(monkeypatch, tmp_path):
    _managed(tmp_path, "mine", "theirs")
    _panes(monkeypatch, mine=[tmp_path / "mine"], theirs=[tmp_path / "theirs"])

    assert [p.key for p in ownership.places_of("mine", _config(_root(tmp_path)))] == ["mine"]


def test_a_nested_place_claims_only_itself(monkeypatch, tmp_path):
    """A pane at the inner place does not also count as occupying the outer one."""
    _managed(tmp_path, "outer", "outer/inner")
    _panes(monkeypatch, work=[tmp_path / "outer" / "inner"])

    assert [p.key for p in ownership.places_of("work", _config(_root(tmp_path)))] == ["outer/inner"]


def test_a_place_whose_directory_is_gone_is_still_owned(monkeypatch, tmp_path):
    """tmux keeps reporting the original path, which is what makes this tossable.

    A session outliving its worktree would otherwise be unresolvable, and the
    only way to close it would be the tmux command this exists to replace.
    """
    _managed(tmp_path, "vanished")
    root = PlaceRoot(
        path=tmp_path, list=f"echo {tmp_path}/vanished", path_of=f"echo {tmp_path}/{{key}}"
    )
    _panes(monkeypatch, ghost=[tmp_path / "vanished"])

    places = ownership.places_of("ghost", _config(root))
    assert [p.key for p in places] == ["vanished"]

    (tmp_path / "vanished" / ".git").rmdir()
    (tmp_path / "vanished").rmdir()

    assert places[0].exists is False


def test_places_span_roots(monkeypatch, tmp_path):
    """A catchall session sitting in two different repos."""
    one, two = tmp_path / "one", tmp_path / "two"
    _managed(one, "a")
    _managed(two, "b")
    _panes(monkeypatch, catchall=[one / "a", two / "b"])

    places = ownership.places_of("catchall", _config(_root(one), _root(two)))

    assert [p.key for p in places] == ["a", "b"]


def test_find_place_searches_every_root(tmp_path):
    """Naming a key is how you act on a place elsewhere; cwd must not narrow it."""
    one, two = tmp_path / "one", tmp_path / "two"
    _managed(two, "wanted")
    (one / "unrelated").mkdir(parents=True)

    place = ownership.find_place(_config(PlaceRoot(path=one), _root(two)), "wanted")

    assert place is not None
    assert place.key == "wanted"
    assert place.root.path == two


def test_find_place_returns_none_for_an_unknown_key(tmp_path):
    assert ownership.find_place(_config(_root(tmp_path)), "nope") is None
