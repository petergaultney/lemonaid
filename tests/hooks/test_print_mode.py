from lemonaid.claude import print_mode


def _tree(monkeypatch, argvs: dict[int, list[str]], parents: dict[int, int]) -> None:
    monkeypatch.setattr(print_mode, "_parent", lambda pid: parents.get(pid, 0))
    monkeypatch.setattr(print_mode.launch_args, "argv", lambda pid: argvs.get(pid, []))


def test_a_claude_ancestor_started_with_dash_p_is_a_print_session(monkeypatch):
    _tree(
        monkeypatch,
        {20: ["sh", "-c", "hook"], 30: ["/usr/local/bin/claude", "-p", "echo ORIG"]},
        {10: 20, 20: 30, 30: 40, 40: 1},
    )

    assert print_mode.is_print_session(10)


def test_an_interactive_claude_is_not(monkeypatch):
    _tree(
        monkeypatch,
        {30: ["claude", "--model", "opus"], 40: ["claude", "-p", "x"]},
        {10: 30, 30: 40, 40: 1},
    )

    assert not print_mode.is_print_session(10)
