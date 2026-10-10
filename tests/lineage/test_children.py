from .shared import lemon, run


def test_children_are_listed_with_their_brief_status_or_none(capsys, monkeypatch):
    parent = lemon("parent", "claude:parent")
    done = lemon("done-child", "codex:done", status="done")
    pending = lemon("pending-child")
    unrelated = lemon("unrelated", status="blocked")
    for child in (done, pending):
        run(capsys, "lemon", "parent", child, "--set", parent, "--json")
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:parent")

    listed = run(capsys, "lemon", "children", "--self", "--json")

    assert listed["lemon_id"] == parent
    assert [(c["lemon_id"], c["status"], c["channel"]) for c in listed["children"]] == [
        (done, "done", "codex:done"),
        (pending, "", ""),
    ]
    assert unrelated not in {c["lemon_id"] for c in listed["children"]}


def test_self_without_an_attached_brief_is_an_error(capsys, monkeypatch):
    monkeypatch.setenv("LEMONAID_CHANNEL", "claude:nobody")

    refused = run(capsys, "lemon", "children", "--self", "--json")

    assert "No brief attached" in refused["error"]
