from lemonaid.inbox import db
from lemonaid.launch.restart import state

from .. import shared


def test_evidence_update_does_not_regress_phase_or_lose_concurrent_fields(tmp_path):
    with db.connect() as conn:
        token = state.reserve(conn, shared.plan(tmp_path))
        state.update(conn, token, "verifying", replacement={"pid": 999})
        state.evidence(conn, token, watcher={"pid": 888})
        operation = state.get(conn, token)
    assert operation["phase"] == "verifying"
    assert operation["evidence"] == {"replacement": {"pid": 999}, "watcher": {"pid": 888}}
