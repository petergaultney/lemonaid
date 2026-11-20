"""A hook's reported thread decides which conversation it is about."""

from lemonaid.codex import notify
from tests import codex_fakes

_THREAD = "01a15bb9-250e-7b00-85b9-1dd66e595f01"


def test_reported_thread_cannot_borrow_an_explicit_sibling_rollout(tmp_path, codex_records):
    sibling = tmp_path / "sibling.jsonl"
    codex_records[_THREAD] = None
    codex_records["01a15bb9-0000-7000-8000-000000000002"] = codex_fakes.thread(
        "01a15bb9-0000-7000-8000-000000000002", "/shared", path=str(sibling)
    )
    assert notify._codex_thread(_THREAD, "/shared", str(sibling)) is None
