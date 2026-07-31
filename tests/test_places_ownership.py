"""Which places a session occupies, derived from tmux rather than recorded.

Nothing is written down when a place is opened, so a directory acquired by hand,
by `place open`, or by an agent all resolve the same way afterward.
"""

from pathlib import Path

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


def test_a_session_owns_the_place_its_pane_sits_in(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, work=[tmp_path / "feat"])

    places = ownership.places_of("work", _config(_root(tmp_path)))

    assert [p.key for p in places] == ["feat"]


def test_a_pane_deep_inside_still_counts_as_the_place(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    (tmp_path / "feat" / "libs" / "thing").mkdir(parents=True)
    _panes(monkeypatch, work=[tmp_path / "feat" / "libs" / "thing"])

    assert [p.key for p in ownership.places_of("work", _config(_root(tmp_path)))] == ["feat"]


def test_several_panes_in_one_place_report_it_once(monkeypatch, tmp_path):
    _managed(tmp_path, "feat")
    _panes(monkeypatch, work=[tmp_path / "feat", tmp_path / "feat", tmp_path / "feat" / "sub"])
    (tmp_path / "feat" / "sub").mkdir()

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


def test_the_innermost_place_wins(monkeypatch, tmp_path):
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


def test_session_holding_finds_the_session_in_a_directory(monkeypatch, tmp_path):
    _panes(monkeypatch, mine=[tmp_path / "here"])
    (tmp_path / "here").mkdir()

    assert ownership.session_holding(tmp_path / "here") == "mine"


def test_session_holding_prefers_an_exact_match(monkeypatch, tmp_path):
    """A session merely in a subdirectory has the weaker claim."""
    (tmp_path / "here" / "sub").mkdir(parents=True)
    _panes(monkeypatch, deeper=[tmp_path / "here" / "sub"], exact=[tmp_path / "here"])

    assert ownership.session_holding(tmp_path / "here") == "exact"


def test_session_holding_is_empty_when_nothing_is_there(monkeypatch, tmp_path):
    _panes(monkeypatch, elsewhere=[tmp_path / "other"])
    (tmp_path / "here").mkdir()

    assert ownership.session_holding(tmp_path / "here") == ""


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
