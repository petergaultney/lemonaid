import subprocess

import pytest

from lemonaid.launch.restart import process


def _ps_fails(monkeypatch, stderr: str) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, stdout="", stderr=stderr),
    )


def test_a_terminal_ps_cannot_find_has_nothing_on_it_even_once_its_name_is_reused(monkeypatch):
    _ps_fails(monkeypatch, "ps: /dev/null: No such file or directory\n")

    assert process.on_tty("/dev/null") == []


def test_any_other_ps_failure_is_an_error(monkeypatch):
    _ps_fails(monkeypatch, "ps: /dev/null: Operation not permitted\n")

    with pytest.raises(ValueError, match="Cannot inventory terminal processes"):
        process.on_tty("/dev/null")
