from lemonaid.inbox.tui.live import status_line


def _status(loop_stall_ms: int) -> str:
    return status_line.inbox_status(2, 3, "tmux", None, False, "", "S", "", loop_stall_ms)


def test_a_loop_stall_is_shown_only_when_there_was_one():
    assert "loop stall" not in _status(0)
    assert _status(920).endswith("[bold red]loop stall:[/] 920 ms")
