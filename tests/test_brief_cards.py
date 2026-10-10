from pathlib import Path

from lemonaid.inbox.tui.brief_cards import BriefCache, CardBrief


def test_cache_reads_attached_brief_and_reloads_after_edit(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text("# Task\n\nStatus: waiting\n\n## Now\n- Waiting on: review\n")
    cache = BriefCache()

    first = cache.get(path)
    assert first is not None
    assert (first.status, first.shown, first.waiting_on) == ("", "idle", "review")
    assert cache.get(path) is first

    path.write_text("# Task\n\nStatus: blocked\n\n## Now\n- Needs Peter: answer\n")
    second = cache.get(path)
    assert second is not None
    assert (second.status, second.waiting_on) == ("blocked", "")
    assert cache.get(tmp_path / "missing.md") is None


def test_the_age_names_the_status_and_how_long_it_has_held_it() -> None:
    assert CardBrief("", "", 0, mid_turn=True, since=1).age(3600) == "active just now"
    assert CardBrief("done", "", 0, since=3540).age(3600) == "done 1m ago"
    assert CardBrief("blocked", "", 0, since=10).age(8 * 3600) == "blocked 7h ago"
    assert CardBrief("blocked", "", 7200).age(3 * 3600) == "blocked 1h ago"  # unrecorded: its edit


def test_cards_follow_the_popup_status_and_now(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text(
        "# Task\n\nStatus: done - PR #12\n\n## Now\n- Waiting on: nothing\n\n"
        "## Context\n```\nStatus: working\n```\n"
    )

    card = BriefCache().get(path)

    assert card is not None
    assert (card.status, card.waiting_on) == ("done", "")


def test_nothing_is_not_a_waiting_subtitle(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text("Status: waiting\n\n## Now\n- Waiting on: nothing\n")

    card = BriefCache().get(path)

    assert card is not None
    assert card.waiting_on == ""


def test_an_unknown_or_missing_status_shows_the_lemon_s_own_state(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.md"
    unknown.write_text("Status: reviewing - soon\n")
    missing = tmp_path / "missing.md"
    missing.write_text("# Task\n\n## Now\n- Next: x\n")

    for path in (unknown, missing):
        card = BriefCache().get(path)
        assert card is not None
        assert (card.status, card.placed, card.shown) == ("", "idle", "idle")


def test_needs_keeps_its_label_in_either_form(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text("Status: waiting\n\n## Now\n### Waiting on\nCI\n\n### Needs Peter\n- a\n- b\n")

    card = BriefCache().get(path)

    assert card is not None
    assert (card.needs_line, card.waiting_line, card.extra_lines(False)) == (
        "Needs Peter: a (+1 more)",
        "CI",
        3,
    )
    assert card.extra_lines(True) == 2


def test_waiting_on_shows_only_while_idle_and_needs_not_once_done() -> None:
    assert CardBrief("", "review", 0).waiting_line == "review"
    assert CardBrief("", "review", 0, mid_turn=True).waiting_line == ""
    assert CardBrief("", "review", 0, mark="dead").waiting_line == "review"
    assert CardBrief("", "", 0, "answer").needs_line == "Needs: answer"
    assert CardBrief("review", "Sam", 0).waiting_line == ""
    assert CardBrief("done", "", 0, "answer").needs_line == ""
    assert CardBrief("blocked", "", 0, "answer").needs_line == "Needs: answer"
    assert CardBrief("merge", "", 0, "PR #9").needs_line == "Needs: PR #9"
    assert CardBrief("review", "", 0, "Sam on PR #9").needs_line == "Needs: Sam on PR #9"
    assert CardBrief("approve", "", 0, "Sam's PR #9").needs_line == "Needs: Sam's PR #9"
    assert CardBrief("alert", "", 0, "disk full").needs_line == "Needs: disk full"


def test_running_shows_its_first_line_only_while_running(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text(
        "# Task\n\nStatus: running\n\n## Now\n\n### Running\n\n- UA run in work:3\n- CI\n"
    )

    card = BriefCache().get(path)

    assert card is not None
    assert card.running_line == "UA run in work:3 (+1 more)"
    assert card.extra_lines(False) == 2
    assert CardBrief("", "", 0, running="UA run").running_line == ""
    assert CardBrief("running", "", 0, since=10).age(8 * 3600) == "running 7h ago"


def test_an_idle_card_shows_how_long_it_has_been_idle() -> None:
    day = 86400
    assert CardBrief("", "", 9 * day, since=day).age(10 * day) == "idle 9 days"
    assert CardBrief("", "", day, since=day).age(2 * day + 60) == "idle 1 day"
    assert CardBrief("", "", 0, since=1).age(3 * 3600) == "idle 2h"
    assert CardBrief("", "", 0, since=3590).age(3600) == "idle just now"
    assert (
        CardBrief("", "", 9 * day, since=day).age(2 * day) == "idle 1 day"
    )  # its brief edit doesn't count


def test_a_brief_without_a_status_shows_the_lemon_s_own_state() -> None:
    assert CardBrief("", "", 0, mid_turn=True).shown == "active"
    assert CardBrief("", "", 0).shown == "idle"
    assert CardBrief("", "", 0, mark="deaf").shown == "deaf"
    assert CardBrief("", "", 0, mark="dead").shown == "dead"
    assert CardBrief("", "", 0, mark="dead").placed == "dead"
    assert CardBrief("", "", 0, mid_turn=True).placed == "active"


def test_a_dead_lemon_whose_turn_never_ended_shows_dead() -> None:
    card = CardBrief("", "", 0, mid_turn=True, mark="dead")
    assert (card.placed, card.shown, card.age(0)) == ("dead", "dead", "dead · idle just now")


def test_a_set_status_shows_unless_held_mid_turn() -> None:
    assert CardBrief("blocked", "", 0, mid_turn=True).shown == "blocked"
    assert CardBrief("blocked", "", 0, mid_turn=True, held_mid_turn=True).shown == "active"
    assert CardBrief("running", "", 0, mid_turn=True, held_mid_turn=True).shown == "running"
    assert CardBrief("blocked", "", 0, mid_turn=True, held_mid_turn=True).placed == "blocked"


def test_a_deaf_or_dead_mark_prefixes_the_age() -> None:
    assert CardBrief("", "", 0, mark="deaf").age(3600) == "deaf · idle 1h"
    assert CardBrief("blocked", "", 0, mark="dead").shown == "blocked"
    assert CardBrief("blocked", "", 0, mark="dead").age(3600) == "dead · blocked 1h ago"
    held = CardBrief("blocked", "", 0, mid_turn=True, held_mid_turn=True)
    assert held.age(3600) == "blocked 1h ago"
