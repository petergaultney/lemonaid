"""`lemonaid watch pr --wait|--status` accept a PR URL as well as a number."""

import pytest

from lemonaid import pr_url
from lemonaid.watch import pr_cli

from .test_watch_pr import _cli, _write_snapshot, fake_gh  # noqa: F401


@pytest.mark.parametrize(
    "suffix", ["", "/", "/files", "#issuecomment-1", "/files?w=1#diff-abc", "?x=1"]
)
def test_url_parses_with_trailing_parts(suffix):
    assert pr_url.parse(f"https://github.com/acme/widgets/pull/249{suffix}") == (
        "acme/widgets",
        "249",
    )


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/acme/widgets/issues/249",
        "https://github.com/acme/widgets/pull/abc",
        "https://example.com/acme/widgets/pull/1",
        "acme/widgets#1",
    ],
)
def test_non_pull_request_urls_are_rejected(text):
    assert pr_url.parse(text) is None


def test_pr_ref_takes_a_number_or_a_url():
    assert pr_cli._pr_ref("90") == ("", 90)
    assert pr_cli._pr_ref("https://github.com/o/r/pull/90/files") == ("o/r", 90)


def test_cli_wait_accepts_a_url(tmp_path, fake_gh):  # noqa: F811
    _write_snapshot(fake_gh, "b" * 40)

    result = _cli(
        tmp_path, "--wait", "https://github.com/o/r/pull/90", "--head", "a" * 40, "--once"
    )

    assert result.returncode == 0
    assert result.stdout == f"PR #90 head moved {'a' * 10} -> {'b' * 10}\n"


def test_cli_status_accepts_a_url(tmp_path, fake_gh):  # noqa: F811
    result = _cli(tmp_path, "--status", "https://github.com/o/r/pull/90#issuecomment-5")

    assert result.stdout == "no waiter running\n"


def test_cli_url_with_a_contradicting_repo_is_an_error(tmp_path, fake_gh):  # noqa: F811
    result = _cli(tmp_path, "--wait", "https://github.com/o/r/pull/90", "--repo", "x/y", "--once")

    assert result.returncode == 2
    assert "contradicts the PR URL's repo o/r" in result.stderr


def test_cli_url_with_the_same_repo_is_fine(tmp_path, fake_gh):  # noqa: F811
    _write_snapshot(fake_gh, "b" * 40)

    result = _cli(
        tmp_path,
        "--wait",
        "https://github.com/o/r/pull/90",
        "--repo",
        "O/R",
        "--head",
        "a" * 40,
        "--once",
    )

    assert result.returncode == 0


@pytest.mark.parametrize(
    "bad", ["https://github.com/o/r/issues/90", "https://example.com/o/r/pull/90", "abc"]
)
def test_cli_rejects_something_that_is_not_a_pull_request(tmp_path, fake_gh, bad):  # noqa: F811
    result = _cli(tmp_path, "--wait", bad, "--once")

    assert result.returncode == 2
    assert "not a PR number or a github.com pull request URL" in result.stderr
