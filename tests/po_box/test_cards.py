import datetime

import pytest

from lemonaid.po_box import cards

_NOW = datetime.datetime(2026, 11, 11, 12, tzinfo=datetime.UTC)


def _register(root, now=_NOW, lemon_id="plan.BlessBar"):
    return cards.register(root, "sam", lemon_id, "Plan the work", "lemonaid", now)


def test_register_writes_a_card_that_reads_back_with_an_inbox(tmp_path):
    card = _register(tmp_path)

    found = cards.read(tmp_path / "lemons" / "sam" / "plan.BlessBar")
    assert found == card
    assert (found.title, found.area) == ("Plan the work", "lemonaid")
    assert found.address == "sam/plan.BlessBar" and found.inbox.is_dir()
    assert found.expires == _NOW + cards.LIFETIME


def test_renewal_keeps_the_first_registration_and_happens_only_when_due(tmp_path):
    card = _register(tmp_path)
    assert cards.renew_if_due(card, _NOW + datetime.timedelta(hours=1)) == card

    later = _NOW + cards.LIFETIME - datetime.timedelta(hours=1)
    renewed = cards.renew_if_due(card, later)
    assert renewed.expires == later + cards.LIFETIME and renewed.registered == _NOW
    assert _register(tmp_path, now=later).registered == _NOW


def test_find_by_name_half_and_refuse_expired_or_missing(tmp_path):
    _register(tmp_path)
    assert cards.find(tmp_path, "sam/BlessBar", _NOW).lemon_id == "plan.BlessBar"
    assert cards.find(tmp_path, "sam/plan.BlessBar", _NOW).lemon_id == "plan.BlessBar"

    with pytest.raises(LookupError, match="expired"):
        cards.find(tmp_path, "sam/BlessBar", _NOW + cards.LIFETIME)
    with pytest.raises(LookupError, match="No lemon"):
        cards.find(tmp_path, "kim/BlessBar", _NOW)
    with pytest.raises(LookupError, match="owner/lemon"):
        cards.find(tmp_path, "BlessBar", _NOW)


def test_registered_is_none_without_a_po_box_root_or_a_card(tmp_path):
    assert cards.registered(None, "sam", "plan.BlessBar") is None
    assert cards.registered(tmp_path, "sam", "plan.BlessBar") is None
    _register(tmp_path)
    assert cards.registered(tmp_path, "sam", "plan.BlessBar") is not None


def test_a_linked_lemon_folder_is_not_a_registration(tmp_path):
    real = _register(tmp_path / "elsewhere").folder
    linked = tmp_path / "lemon-post" / "lemons" / "sam" / "plan.BlessBar"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(real)

    assert cards.registered(tmp_path / "lemon-post", "sam", "plan.BlessBar") is None
