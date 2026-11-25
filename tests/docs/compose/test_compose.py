"""Fitting an event's offers under Claude's cap."""

from lemonaid.docs import compose, frontmatter, offers, start


def _offer(path, body: str) -> offers.Offer:
    path.write_text(body)
    return offers.Offer(frontmatter.Doc(path=path), "", {"package": "team"})


def _state() -> dict:
    return {"calls": 0, "delivered": {}, "shadowed": {}}


def test_many_docs_too_long_to_fit_are_named_within_the_cap(tmp_path):
    state = _state()
    given = [_offer(tmp_path / f"long-{i}.md", "x" * 10_000) for i in range(70)]

    first = compose.compose(state, {}, given, compose.CLAUDE_LIMIT)
    second = compose.compose(state, {}, given, compose.CLAUDE_LIMIT)

    assert 0 < len(first.context()) <= compose.CLAUDE_LIMIT
    assert len(second.context()) <= compose.CLAUDE_LIMIT
    named = {e["doc"] for o in (first, second) for e in o.entries}
    assert len(named) == len(first.entries) + len(second.entries)


def test_a_pointer_that_doesn_t_fit_waits_for_a_later_call(tmp_path):
    state = _state()
    most = compose.CLAUDE_LIMIT - len(compose._REFUSAL)
    big = tmp_path / "big.md"
    nearly_full = _offer(big, "b" * (most - len(start.block(big, "")) - 10))
    too_long = _offer(tmp_path / "huge.md", "h" * 20_000)

    first = compose.compose(state, {}, [nearly_full, too_long], compose.CLAUDE_LIMIT)
    second = compose.compose(state, {}, [nearly_full, too_long], compose.CLAUDE_LIMIT)

    assert [e["delivery"] for e in first.entries] == ["full"]
    assert [e["delivery"] for e in second.entries] == ["pointer"]
