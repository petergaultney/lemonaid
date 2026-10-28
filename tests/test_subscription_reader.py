import os

import pytest

from lemonaid.watch import roles, subscription_state


@pytest.fixture
def reading(tmp_path, monkeypatch):
    brief = tmp_path / "brief.md"
    brief.write_text("# Parent\n\nBrief-ID: parent.IndexElf\n")
    root = tmp_path / "cursors"
    calls = []
    original = subscription_state.read

    def counted(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(subscription_state, "read", counted)
    poll = subscription_state.reader(brief, root, tmp_path, "parent.IndexElf", ())
    poll(frozenset())
    poll(frozenset())  # Cursor initialization changes its own input versions once.
    calls.clear()
    return brief, root, poll, calls


def test_idle_polls_reuse_the_parsed_subscriptions(reading):
    _, _, poll, calls = reading
    first = poll(frozenset())
    for _ in range(20):
        assert poll(frozenset()) is first
    assert not calls


def test_a_same_size_edit_with_restored_mtime_is_read(reading):
    brief, _, poll, calls = reading
    stat = brief.stat()
    brief.write_text(brief.read_text().replace("Parent", "Edited"))
    os.utime(brief, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    poll(frozenset())
    assert len(calls) == 1


def test_an_atomic_replacement_is_read_and_a_missing_brief_still_raises(reading):
    brief, _, poll, calls = reading
    replacement = brief.with_suffix(".tmp")
    replacement.write_text(brief.read_text())
    replacement.replace(brief)
    poll(frozenset())
    assert len(calls) == 1
    brief.unlink()
    with pytest.raises(FileNotFoundError):
        poll(frozenset())


def test_an_edit_during_a_read_is_not_cached_under_the_new_version(reading, monkeypatch):
    brief, _, poll, _ = reading
    original = subscription_state.read
    brief.write_text("# First edit\n")

    def edit_after_read(*args):
        result = original(*args)
        brief.write_text("# Second edit\n\n## Watching\n- `invalid command`\n")
        monkeypatch.setattr(subscription_state, "read", original)
        return result

    monkeypatch.setattr(subscription_state, "read", edit_after_read)
    assert poll(frozenset())[1] == ""
    assert "invalid command" in poll(frozenset())[1]


def test_child_pr_changes_refresh_the_parent_role(reading):
    brief, _, poll, _ = reading
    brief.write_text(
        brief.read_text()
        + "\n## PRs\n\n| Work | PR | Review |\n|---|---|---|\n"
        + "| Change | [repo#1](https://github.com/example/repo/pull/1) | |\n"
    )
    specs, _ = poll(frozenset())
    assert next(spec.role for spec in specs if spec.kind == "pr") == roles.AUTHOR
    specs, _ = poll(frozenset({("example/repo", "1")}))
    assert next(spec.role for spec in specs if spec.kind == "pr") == roles.PARENT


def test_delivered_problems_and_a_changed_fallback_invalidate_the_cache(reading, tmp_path):
    brief, root, poll, _ = reading
    brief.write_text("\n")
    _, problem = poll(frozenset())
    assert "Incomplete brief header" in problem
    subscription_state.remember(root, problem)
    assert poll(frozenset())[1] == ""

    watched = tmp_path / "new-file"
    (root / "subscriptions.md").write_text(
        f"# Parent\n\n## Watching\n- `lemonaid watch file --wait {watched}`\n"
    )
    specs, _ = poll(frozenset())
    assert any(spec.kind == "file" and spec.target == (str(watched),) for spec in specs)


def test_periodic_refresh_resolves_retargeted_symlinks(reading, tmp_path, monkeypatch):
    brief, _, poll, _ = reading
    first, second, link = (tmp_path / name for name in ("first", "second", "link"))
    first.touch()
    second.touch()
    link.symlink_to(first)
    brief.write_text(f"# Parent\n\n## Watching\n- `lemonaid watch file --wait {link}`\n")
    now = subscription_state.time.monotonic()
    monkeypatch.setattr(subscription_state.time, "monotonic", lambda: now)
    poll(frozenset())
    poll(frozenset())
    link.unlink()
    link.symlink_to(second)
    now += 31
    specs, _ = poll(frozenset())
    assert next(spec.target for spec in specs if spec.kind == "file") == (str(second),)
