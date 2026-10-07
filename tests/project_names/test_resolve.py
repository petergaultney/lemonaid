import subprocess

import pytest

from lemonaid.config import PlaceRoot
from lemonaid.inbox.tui import project_names


@pytest.mark.parametrize(
    "command, expected",
    [
        ("printf 'tools/relay\\n'", "tools/relay"),
        ("printf '\\n  tools/relay  \\n\\n'", "tools/relay"),
        ("true", ""),
        ("printf 'one\\ntwo\\n'", ""),
        ("printf 'ignored'; exit 1", ""),
        ("printf '\\377'", ""),
    ],
)
def test_hook_output(tmp_path, command, expected):
    assert (
        project_names.resolve(PlaceRoot(tmp_path, project_name=command), str(tmp_path)) == expected
    )


def test_directory_argument_is_quoted_and_command_runs_at_root(tmp_path):
    directory = str(tmp_path / "space ' ; $(echo injected)")
    root = PlaceRoot(
        tmp_path, project_name='test "$PWD" = ' + str(tmp_path) + "; printf '%s\\n' {dir}"
    )
    assert project_names.resolve(root, directory) == directory


def test_timeout_keeps_fallback(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    assert project_names.resolve(PlaceRoot(tmp_path, project_name="sleep 30"), str(tmp_path)) == ""
