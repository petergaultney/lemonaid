import subprocess
import sys


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lemonaid", *argv],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=20,
    )


def test_bare_inbox_without_tty_prints_help_and_exits():
    result = _run("inbox")

    assert result.returncode == 0
    assert "usage: lemonaid inbox" in result.stdout
    assert "list" in result.stdout


def test_lma_without_tty_prints_help_and_exits():
    result = subprocess.run(
        [sys.executable, "-c", "from lemonaid.cli import inbox_main; inbox_main()"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=20,
    )

    assert result.returncode == 0
    assert "usage: lma" in result.stdout
