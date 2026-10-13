"""A doc waiter warns when the name it signs as is held by more than one active lemon."""

from lemonaid.brief import identity, store
from lemonaid.inbox import db
from lemonaid.watch import shared_signer


def _brief(lemon_id: str) -> None:
    path = store.briefs_dir() / f"{lemon_id.split('.')[0]}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# x\n\nBrief-ID: {lemon_id}\n")
    with db.connect() as conn:
        identity.ensure(conn, path)


def test_a_shared_signing_name_warns_naming_both_lemons():
    _brief("one.AuditInk")
    _brief("two.AuditInk")

    warning = shared_signer.warning("Reviewer (AuditInk)")

    assert "AuditInk is the name of one.AuditInk, two.AuditInk" in warning


def test_a_name_one_lemon_holds_does_not_warn():
    _brief("one.AuditInk")

    assert shared_signer.warning("Reviewer (AuditInk)") == ""
    assert shared_signer.warning("Peter") == ""
