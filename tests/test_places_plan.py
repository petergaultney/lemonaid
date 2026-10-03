"""What a toss aimed at one place would close.

The planner is pure: panes in, a classification of windows and sessions out.
Every rule about what counts as 'in the place' and 'dedicated to the place' is
tested here, against snapshots shaped like tmux's.
"""

from pathlib import Path

from lemonaid.config import PlaceRoot
from lemonaid.places import ownership, plan


def _root(tmp_path: Path) -> PlaceRoot:
    return PlaceRoot(path=tmp_path, destroy="release {key}")


def _places(tmp_path: Path, *keys: str) -> list[ownership.Place]:
    root = _root(tmp_path)
    for key in keys:
        (tmp_path / key).mkdir(parents=True, exist_ok=True)

    return [ownership.Place(key, root, tmp_path / key) for key in keys]


def _pane(session: str, window: str, pane: str, path: Path | None) -> ownership.Pane:
    return ownership.Pane(session, window, pane, path)


def _only(planned: plan.Plan) -> plan.SessionPlan:
    assert len(planned.sessions) == 1, planned
    return planned.sessions[0]


def test_a_session_named_for_the_place_is_dedicated_to_it(tmp_path):
    """What `place open` makes, exactly: every window in the worktree."""
    (feat,) = places = _places(tmp_path, "feat")
    panes = [
        _pane("feat", "@1", "%1", feat.directory),
        _pane("feat", "@2", "%2", feat.directory),
        _pane("feat", "@4", "%4", feat.directory / "libs"),
    ]

    session = _only(plan.plan_toss(feat, panes, places))

    assert session.dedicated
    assert session.tied == ["@1", "@2", "@4"]
    assert session.windows == ["@1", "@2", "@4"]


def test_a_stray_shell_does_not_undedicate_a_session_named_for_the_place(tmp_path):
    """A shell that cd-ed home is still part of the session opened for this work."""
    (feat,) = places = _places(tmp_path, "feat")
    panes = [
        _pane("feat", "@1", "%1", feat.directory),
        _pane("feat", "@3", "%3", Path.home()),
    ]

    session = _only(plan.plan_toss(feat, panes, places))

    assert session.dedicated
    assert session.other == ["@3"]


def test_the_name_is_compared_as_tmux_spells_it(tmp_path):
    """tmux forbids dots in session names, so `place open v1.2` makes session 'v1-2'."""
    (place,) = places = _places(tmp_path, "v1.2")

    session = _only(plan.plan_toss(place, [_pane("v1-2", "@1", "%1", place.directory)], places))

    assert session.dedicated


def test_a_session_entirely_in_the_place_is_dedicated_whatever_its_name(tmp_path):
    (feat,) = places = _places(tmp_path, "feat")

    session = _only(plan.plan_toss(feat, [_pane("work", "@1", "%1", feat.directory)], places))

    assert session.dedicated


def test_an_unnamed_session_with_a_window_elsewhere_is_not_dedicated(tmp_path):
    """Only the session's name says the stray window belongs to this work."""
    (feat,) = places = _places(tmp_path, "feat")
    panes = [
        _pane("work", "@1", "%1", feat.directory),
        _pane("work", "@3", "%3", Path.home()),
    ]

    session = _only(plan.plan_toss(feat, panes, places))

    assert not session.dedicated
    assert session.tied == ["@1"]
    assert session.other == ["@3"]


def test_a_session_holding_another_place_is_shared(tmp_path):
    """The case this exists for: one session, several worktrees, one of them merged."""
    merged, live, other = places = _places(tmp_path, "feat/merged", "feat/live", "feat/other")
    panes = [
        _pane("katamari", "@1", "%1", live.directory),
        _pane("katamari", "@4", "%4", merged.directory),
        _pane("katamari", "@7", "%7", merged.directory / "src"),
        _pane("katamari", "@9", "%9", other.directory),
    ]

    session = _only(plan.plan_toss(merged, panes, places))

    assert not session.dedicated
    assert session.tied == ["@4", "@7"]
    assert session.other == ["@1", "@9"]
    assert session.other_places == ["feat/live", "feat/other"]


def test_a_session_named_for_the_place_but_holding_another_is_shared(tmp_path):
    """The name says what it started as; the other worktree says what it became."""
    base, on_top = places = _places(tmp_path, "base", "on-top")
    panes = [
        _pane("base", "@1", "%1", base.directory),
        _pane("base", "@2", "%2", on_top.directory),
    ]

    session = _only(plan.plan_toss(base, panes, places))

    assert not session.dedicated
    assert session.other_places == ["on-top"]


def test_a_protected_place_does_not_make_a_session_shared(tmp_path):
    """Everyone passes through the trunk worktree; a window there is not other work."""
    feat, main = places = _places(tmp_path, "feat", "main")
    panes = [
        _pane("feat", "@1", "%1", feat.directory),
        _pane("feat", "@2", "%2", main.directory),
    ]

    session = _only(plan.plan_toss(feat, panes, places))

    assert session.dedicated
    assert session.other_places == []
    assert session.other == ["@2"]


def test_a_mixed_window_is_a_refusal(tmp_path):
    """Closing it would take the other pane; leaving it would strand this one."""
    feat, other = places = _places(tmp_path, "feat", "other")
    panes = [
        _pane("work", "@1", "%1", feat.directory),
        _pane("work", "@1", "%2", other.directory),
    ]

    planned = plan.plan_toss(feat, panes, places)

    session = _only(planned)
    assert session.mixed == ["@1"]
    assert not session.dedicated
    assert len(planned.refusals) == 1
    assert "@1" in planned.refusals[0]
    assert "%1" in planned.refusals[0] and "%2" in planned.refusals[0]
    assert str(other.directory) in planned.refusals[0]


def test_a_pane_with_no_path_makes_its_window_mixed(tmp_path):
    """tmux could not say where it is, so it cannot be assumed to be in the place."""
    (feat,) = places = _places(tmp_path, "feat")
    panes = [
        _pane("work", "@1", "%1", feat.directory),
        _pane("work", "@1", "%2", None),
    ]

    planned = plan.plan_toss(feat, panes, places)

    assert _only(planned).mixed == ["@1"]
    assert "(no path)" in planned.refusals[0]


def test_a_pane_in_a_nested_place_is_not_in_the_outer_one(tmp_path):
    outer, inner = places = _places(tmp_path, "outer", "outer/inner")
    panes = [
        _pane("work", "@1", "%1", outer.directory),
        _pane("work", "@2", "%2", inner.directory),
    ]

    session = _only(plan.plan_toss(outer, panes, places))

    assert session.tied == ["@1"]
    assert session.other == ["@2"]
    assert session.other_places == ["outer/inner"]


def test_every_session_with_a_pane_in_the_place_is_planned(tmp_path):
    """An onlooker that cd-ed into the worktree shows up alongside the real session."""
    (feat,) = places = _places(tmp_path, "feat")
    panes = [
        _pane("feat", "@1", "%1", feat.directory),
        _pane("hq", "@8", "%8", feat.directory / "docs"),
        _pane("hq", "@9", "%9", Path.home()),
    ]

    planned = plan.plan_toss(feat, panes, places)

    assert [s.name for s in planned.sessions] == ["feat", "hq"]
    assert planned.sessions[0].dedicated
    assert not planned.sessions[1].dedicated
    assert planned.sessions[1].tied == ["@8"]


def test_a_session_with_no_pane_in_the_place_is_not_planned(tmp_path):
    feat, other = places = _places(tmp_path, "feat", "other")

    planned = plan.plan_toss(feat, [_pane("elsewhere", "@1", "%1", other.directory)], places)

    assert planned.sessions == []
    assert planned.refusals == []


def test_the_place_may_be_gone_already(tmp_path):
    """tmux keeps reporting the old path, which is what lets the session be found."""
    root = _root(tmp_path)
    gone = ownership.Place("gone", root, tmp_path / "gone")

    session = _only(plan.plan_toss(gone, [_pane("gone", "@1", "%1", tmp_path / "gone")], [gone]))

    assert session.dedicated
