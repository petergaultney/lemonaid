"""Group order survives default folding; an arranger can still choose its own order."""

from types import SimpleNamespace

import pytest

from lemonaid import inbox
from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.inbox.tui.live.inbox_arrange import Arrangement


@pytest.mark.parametrize("reply", [None, {"error": "unavailable"}, {"rows": [2], "folded": [1]}])
def test_group_order_uses_default_order_until_an_arranger_answers(reply):
    older = db.Notification(1, "older", "", status="read")
    newer = db.Notification(2, "newer", "", status="read")
    active = inbox.view.Active([older, newer], {}, {}, frozenset())
    arrangement = Arrangement(Config())
    arrangement._arranger = SimpleNamespace(answer=lambda *args: reply, error="")

    shown, folded, _, group_order = arrangement.arranged(
        active, [newer], [older], frozenset(), frozenset(), {}, False, 120
    )

    assert arrangement.parents_first == (not reply or "rows" not in reply)
    assert shown == [newer] and folded == [older]
    assert group_order == ([newer, older] if reply and "rows" in reply else active.rows)
