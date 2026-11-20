import datetime

from lemonaid.brief import flags
from lemonaid.messages import store
from lemonaid.po_box import cards, enrollment
from lemonaid.po_box_config import PoBoxConfig

_NOW = datetime.datetime(2026, 11, 12, 12, tzinfo=datetime.UTC)
_ON = "---\npo-box: true\narea: lemonaid\n---\n# Plan the work\n"


def _config(tmp_path, root=True) -> PoBoxConfig:
    if root:
        (tmp_path / "lemon-post").mkdir()
    return PoBoxConfig(root=tmp_path / "lemon-post", owner="sam")


def _sync(config, brief, now=_NOW):
    return enrollment.sync(config, brief, store.mailbox_for_id("plan.BlessBar"), now)


def test_the_toggle_opens_a_box_named_for_the_brief(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(_ON)

    card = _sync(_config(tmp_path), brief)

    assert card is not None and (card.title, card.area) == ("Plan the work", "lemonaid")
    assert cards.read(card.folder) == card


def test_the_toggle_reads_as_a_header_line(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(
        flags.with_flag("# Plan the work\n\nBrief-ID: plan.BlessBar\n", "PO box", True)
    )

    assert _sync(_config(tmp_path), brief) is not None


def test_a_renamed_brief_rewrites_its_card_keeping_the_registration_time(tmp_path):
    config, brief = _config(tmp_path), tmp_path / "brief.md"
    brief.write_text(_ON)
    first = _sync(config, brief)
    brief.write_text(_ON.replace("Plan the work", "Plan more work"))

    later = _sync(config, brief, _NOW + datetime.timedelta(hours=1))

    assert later.title == "Plan more work" and later.registered == first.registered


def test_a_done_brief_closes_its_box(tmp_path):
    config, brief = _config(tmp_path), tmp_path / "brief.md"
    brief.write_text(_ON)
    card = _sync(config, brief)
    brief.write_text(_ON.replace("po-box: true", "po-box: true\nstatus: done"))

    assert _sync(config, brief) is None
    assert not card.folder.exists()


def test_an_unattached_shared_folder_is_never_created(tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text(_ON)

    assert _sync(_config(tmp_path, root=False), brief) is None
    assert not (tmp_path / "lemon-post").exists()


def test_an_unreadable_brief_leaves_the_box_open(tmp_path):
    config, brief = _config(tmp_path), tmp_path / "brief.md"
    brief.write_text(_ON)
    card = _sync(config, brief)
    brief.write_text("---\n: [\n---\n# broken\n")

    assert _sync(config, brief) == card


def test_a_done_status_line_closes_the_box_too(tmp_path):
    config, brief = _config(tmp_path), tmp_path / "brief.md"
    text = "# Plan the work\n\nBrief-ID: plan.BlessBar\nPO box: yes\n"
    brief.write_text(text)
    card = _sync(config, brief)
    brief.write_text(text.replace("PO box: yes", "PO box: yes\nStatus: done"))

    assert _sync(config, brief) is None and not card.folder.exists()


def test_a_linked_card_folder_is_never_written_through(tmp_path):
    config, brief = _config(tmp_path), tmp_path / "brief.md"
    brief.write_text(_ON)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / cards.CARD).write_text("theirs")
    (config.root / "lemons" / "sam").mkdir(parents=True)
    (config.root / "lemons" / "sam" / "plan.BlessBar").symlink_to(outside)

    assert _sync(config, brief) is None and _sync(config, brief) is None
    assert (outside / cards.CARD).read_text() == "theirs"
    assert sorted(p.name for p in outside.iterdir()) == [cards.CARD]
