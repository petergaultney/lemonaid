from pathlib import Path

from lemonaid.inbox.tui.brief_cards import BriefCache, CardBrief


def test_cache_reads_attached_brief_and_reloads_after_edit(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text("# Task\n\nStatus: waiting\n\n## Now\n- Waiting on: review\n")
    cache = BriefCache()

    first = cache.get(path)
    assert first is not None
    assert (first.status, first.waiting_on) == ("waiting", "review")
    assert cache.get(path) is first

    path.write_text("# Task\n\nStatus: blocked\n\n## Now\n- Needs Peter: answer\n")
    second = cache.get(path)
    assert second is not None
    assert (second.status, second.waiting_on) == ("blocked", "")
    assert cache.get(tmp_path / "missing.md") is None


def test_only_active_statuses_get_stale_hint() -> None:
    assert CardBrief("working", "", 0).age(8 * 3600, 6) == "updated 8h ago (stale)"
    assert CardBrief("waiting", "", 0).age(3600, 6) == "updated 1h ago"
    assert CardBrief("done", "", 0).age(8 * 3600, 6) == "updated 8h ago"


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


def test_unknown_status_has_no_card_state(tmp_path: Path) -> None:
    path = tmp_path / "brief.md"
    path.write_text("Status: reviewing - soon\n")

    assert BriefCache().get(path) is None
