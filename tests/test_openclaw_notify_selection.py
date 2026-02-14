"""Tests for OpenClaw register session selection heuristics."""

from pathlib import Path

from lemonaid.openclaw.notify import _pick_session_candidate, _session_id_matches


def test_session_id_matches_exact_and_prefix():
    full_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert _session_id_matches(full_id, full_id) is True
    assert _session_id_matches("a1b2c3d4", full_id) is True


def test_pick_candidate_prefers_non_excluded_session():
    a_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    b_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    candidates = [
        (Path("/a.jsonl"), a_id, "agent-a", "/home/peter/clawd"),
        (Path("/b.jsonl"), b_id, "agent-b", "/home/peter/clawd"),
    ]

    selected = _pick_session_candidate(
        candidates, requested_session_id=None, excluded_session_ids={a_id}
    )
    assert selected[1] == b_id


def test_pick_candidate_with_requested_session_id():
    wanted = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    candidates = [
        (Path("/a.jsonl"), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "agent-a", "/home/peter/clawd"),
        (Path("/b.jsonl"), wanted, "agent-b", "/home/peter/clawd"),
    ]

    selected = _pick_session_candidate(
        candidates, requested_session_id="bbbbbbbb", excluded_session_ids=set()
    )
    assert selected[1] == wanted


def test_pick_candidate_falls_back_when_all_excluded():
    only_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    candidates = [(Path("/a.jsonl"), only_id, "agent-a", "/home/peter/clawd")]
    selected = _pick_session_candidate(
        candidates, requested_session_id=None, excluded_session_ids={only_id}
    )
    assert selected[1] == only_id
