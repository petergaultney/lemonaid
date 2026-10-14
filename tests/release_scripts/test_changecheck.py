"""scripts/changecheck.py: what CI lets a PR do to changes/, CHANGES.md and the version."""

from .shared import changecheck

_FILES = {
    "changes/2026-10-14-new-feature.md": "# Minor\n\n- **A feature.**\n",
    "changes/2026-10-14-other-feature.md": "# Patch\n\n- **Another.**\n",
    "changes/2026-10-14-bad-file.md": "- no heading\n",
    "changes/new-feature.md": "# Minor\n\n- **Misnamed.**\n",
}
_ADDED = ("A", "changes/2026-10-14-new-feature.md")


def _check(changed, base="0.115.3", head="0.115.3"):
    return list(changecheck.check(base, head, changed, _FILES.__getitem__))


def test_one_added_change_file_passes():
    assert _check([("M", "src/x.py"), ("M", "changes/README.md"), _ADDED]) == []


def test_no_change_file_fails():
    assert _check([("M", "src/x.py")]) == ["a PR adds exactly one change file; this one adds 0"]


def test_two_change_files_fail():
    changed = [_ADDED, ("A", "changes/2026-10-14-other-feature.md")]
    assert _check(changed) == ["a PR adds exactly one change file; this one adds 2"]


def test_malformed_or_misnamed_change_file_fails():
    assert len(_check([("A", "changes/2026-10-14-bad-file.md")])) == 1
    assert len(_check([("A", "changes/new-feature.md")])) == 1


def test_editing_changes_md_an_old_change_file_or_the_version_fails():
    assert len(_check([_ADDED, ("M", "CHANGES.md")])) == 1
    assert len(_check([_ADDED, ("M", "changes/2026-10-01-older-change.md")])) == 1
    assert len(_check([_ADDED, ("D", "changes/2026-10-01-older-change.md")])) == 1
    assert len(_check([_ADDED, ("M", "pyproject.toml")], head="0.116.0")) == 1


def test_pr_changing_nothing_under_src_needs_no_change_file():
    assert _check([("M", "docs/config.md"), ("A", "tests/test_x.py"), ("M", "README.md")]) == []
    assert _check([("M", "scripts/release.py"), ("M", ".github/workflows/ci.yml")]) == []
    assert _check([]) == []


def test_pr_changing_src_needs_a_change_file():
    assert len(_check([("M", "src/lemonaid/x.py")])) == 1
    assert len(_check([("M", "src/lemonaid/x.py"), ("M", "docs/config.md")])) == 1
    assert len(_check([("D", "src/lemonaid/x.py")])) == 1


def test_packaged_doc_needs_a_change_file():
    assert len(_check([("M", "docs/for-lemons.md")])) == 1
    assert _check([("M", "docs/other.md"), ("M", "docs/src/for-lemons.md")]) == []


def test_paths_merely_containing_src_do_not_count():
    assert _check([("M", "docs/src/x.md"), ("M", "tests/src/x.py"), ("M", "srcs/x.py")]) == []


def test_pr_outside_src_still_fails_the_conflict_guard():
    assert len(_check([("M", "docs/x.md"), ("M", "CHANGES.md")])) == 1
    assert len(_check([("M", "docs/x.md")], head="0.116.0")) == 1
    assert len(_check([("M", "tests/x.py"), ("M", "changes/2026-10-01-older-change.md")])) == 1


def test_pr_outside_src_may_add_a_change_file():
    assert _check([("M", "docs/x.md"), _ADDED]) == []
