from pathlib import Path

from lemonaid.hooks import tool_calls


def test_a_claude_file_tool_s_path_is_relative_to_the_session():
    data = {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}, "cwd": "/repo"}

    assert tool_calls.written(data) == [Path("/repo/src/app.py")]


def test_a_codex_patch_writes_the_files_it_adds_updates_and_moves_to():
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Add File: notes/new.md",
            "+hello",
            "*** Update File: src/app.py",
            "*** Move to: src/main.py",
            "@@",
            "-a",
            "+b",
            "*** Delete File: old.txt",
            "*** End Patch",
        ]
    )
    data = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": "/repo"}

    assert tool_calls.written(data) == [
        Path("/repo/notes/new.md"),
        Path("/repo/src/app.py"),
        Path("/repo/src/main.py"),
    ]
    assert tool_calls.created(data) == [Path("/repo/notes/new.md"), Path("/repo/src/main.py")]
    assert list(tool_calls.commands(data["tool_input"])) == []


def test_a_shell_command_writes_nothing_it_can_name():
    assert (
        tool_calls.written({"tool_name": "Bash", "tool_input": {"command": "echo x > a.md"}}) == []
    )


def test_a_patch_inside_a_codex_exec_script():
    script = (
        'await tools.apply_patch("*** Begin Patch\\n*** Add File: notes/new.md\\n+hi\\n'
        '*** End Patch\\n");\n'
        'text(await tools.exec_command({cmd: "gh pr create --draft"}));'
    )
    data = {"tool_name": "exec", "tool_input": {"input": script}, "cwd": "/repo"}

    assert tool_calls.written(data) == [Path("/repo/notes/new.md")]
    assert tool_calls.created(data) == [Path("/repo/notes/new.md")]
    assert list(tool_calls.commands(data["tool_input"])) == ["gh pr create --draft"]


def test_a_patch_that_edits_code_calling_apply_patch_names_its_own_files():
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: src/tool.py",
            '+    tools.apply_patch("*** Begin Patch\\n*** Add File: other.md\\n")',
            "*** End Patch",
        ]
    )
    data = {"tool_name": "apply_patch", "tool_input": {"command": patch}, "cwd": "/repo"}

    assert tool_calls.written(data) == [Path("/repo/src/tool.py")]
