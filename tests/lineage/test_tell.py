from lemonaid.messages import store

from .shared import lemon, run


def _messages(lemon_id: str) -> list[str]:
    return [p.read_text() for p in sorted(store.inbox_for_id(lemon_id).glob("*.md"))]


def test_tell_parent_reaches_the_parent_by_its_link(capsys, monkeypatch):
    parent = lemon("parent", "claude:parent")
    child = lemon("child", "claude:child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:child")

    run(capsys, "tell", "--parent", "PR is up")

    [message] = _messages(parent)
    assert message.startswith(f"From: {child}")
    assert message.endswith("PR is up\n")


def test_tell_child_reaches_a_child_whose_lemon_has_not_started(capsys, monkeypatch):
    parent = lemon("parent", "claude:parent")
    child = lemon("child")
    run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")

    run(capsys, "tell", "--child", child, "Read your brief")

    [message] = _messages(child)
    assert message.endswith("Read your brief\n")


def test_tell_child_refuses_a_lemon_that_is_not_a_child(capsys, monkeypatch):
    lemon("parent", "claude:parent")
    stranger = lemon("stranger", "claude:stranger")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")

    refused = run(capsys, "tell", "--child", stranger, "hello")

    assert "not a child" in refused["err"]
    assert not store.inbox_for_id(stranger).exists()


def test_tell_parent_without_a_link_says_how_to_add_one(capsys, monkeypatch):
    lemon("orphan", "claude:orphan")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:orphan")

    refused = run(capsys, "tell", "--parent", "hello")

    assert "no parent link" in refused["err"]
