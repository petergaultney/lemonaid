import shlex

import pytest

from lemonaid import resume
from lemonaid.config import BackendConfig, Config


@pytest.mark.parametrize("backend", ["claude", "codex"])
def test_missing_directory_uses_surviving_parent(tmp_path, backend):
    removed = tmp_path / "removed"
    cwd, argv = resume.build_resume_command(
        Config(), f"{backend}:id", {"cwd": str(removed), "session_id": "id"}
    )
    assert cwd == str(tmp_path)
    assert not removed.exists()
    assert argv == (
        ["codex", "resume", "id", "--cd", str(tmp_path)]
        if backend == "codex"
        else ["lemonaid", "claude", "resume", "id"]
    )


def test_codex_custom_resume_flags_survive(tmp_path):
    config = Config(
        backends={"codex": BackendConfig(resume_command="codex --no-daemon resume {session_id}")}
    )
    assert resume.build_resume_command(
        config, "codex:id", {"cwd": str(tmp_path / "gone"), "session_id": "id"}
    ) == (str(tmp_path), ["codex", "--no-daemon", "resume", "id", "--cd", str(tmp_path)])


def test_unknown_backend_cannot_resume_in_a_missing_directory(tmp_path):
    config = Config(backends={"other": BackendConfig(resume_command="other resume {session_id}")})
    assert (
        resume.build_resume_command(
            config, "other:id", {"cwd": str(tmp_path / "gone"), "session_id": "id"}
        )
        is None
    )


def test_missing_session_details_cannot_start_a_new_session(tmp_path):
    assert (
        resume.build_resume_command(Config(), "codex:id", {"cwd": str(tmp_path / "gone")}) is None
    )


@pytest.mark.parametrize("option", ["--cd", "-C", "--cd=", "-C="])
def test_configured_codex_directory_is_kept_without_duplicate_flags(tmp_path, option):
    chosen = tmp_path / "chosen directory"
    chosen.mkdir()
    argument = (
        option + shlex.quote(str(chosen))
        if option.endswith("=")
        else option + " " + shlex.quote(str(chosen))
    )
    config = Config(
        backends={
            "codex": BackendConfig(
                resume_command=f"codex --no-daemon resume {{session_id}} {argument}"
            )
        }
    )
    cwd, argv = resume.build_resume_command(
        config, "codex:id", {"cwd": str(tmp_path / "gone"), "session_id": "id"}
    )
    assert cwd == str(chosen)
    assert argv == [
        "codex",
        "--no-daemon",
        "resume",
        "id",
        *([f"{option}{chosen}"] if option.endswith("=") else [option, str(chosen)]),
    ]
    assert not (tmp_path / "gone").exists()


def test_missing_configured_codex_directory_uses_its_surviving_parent(tmp_path):
    chosen = tmp_path / "other" / "removed"
    chosen.parent.mkdir()
    config = Config(
        backends={
            "codex": BackendConfig(
                resume_command="codex resume {session_id} -C " + shlex.quote(str(chosen))
            )
        }
    )
    assert resume.build_resume_command(
        config, "codex:id", {"cwd": str(tmp_path / "gone"), "session_id": "id"}
    ) == (str(chosen.parent), ["codex", "resume", "id", "-C", str(chosen.parent)])


@pytest.mark.parametrize("argument", ["--cd {cwd}", "-C {cwd}", "--cd={cwd}"])
def test_configured_recorded_directory_is_replaced_when_removed(tmp_path, argument):
    config = Config(
        backends={
            "codex": BackendConfig(
                resume_command="codex --no-daemon resume {session_id} " + argument
            )
        }
    )
    cwd, argv = resume.build_resume_command(
        config, "codex:id", {"cwd": str(tmp_path / "gone"), "session_id": "id"}
    )
    assert cwd == str(tmp_path)
    expected = (
        [f"--cd={tmp_path}"]
        if argument.startswith("--cd=")
        else [argument.split()[0], str(tmp_path)]
    )
    assert argv == ["codex", "--no-daemon", "resume", "id", *expected]
