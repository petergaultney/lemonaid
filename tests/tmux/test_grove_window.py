import subprocess

from lemonaid.tmux import grove_window

_BOUND = "bind-key -T prefix Space run-shell -b 'tmux new-session -d -s _lma_grove_window ...'\n"


def _tmux(monkeypatch, platform="darwin", keys=_BOUND, running=False):
    calls = []

    def run(args):
        calls.append(args[0])
        out = keys if args[0] == "list-keys" else ""
        code = 0 if args[0] != "has-session" or running else 1
        return subprocess.CompletedProcess(args, code, out, "")

    monkeypatch.setattr(grove_window.sys, "platform", platform)
    monkeypatch.setattr(grove_window.command, "run", run)
    return calls


def test_the_window_is_started_ahead_of_its_summon_key_once(monkeypatch):
    calls = _tmux(monkeypatch)
    grove_window.warm()
    assert calls == ["list-keys", "has-session", "new-session"]

    calls = _tmux(monkeypatch, running=True)
    grove_window.warm()
    assert calls == ["list-keys", "has-session"]


def test_without_a_summon_key_or_off_macos_nothing_starts(monkeypatch):
    calls = _tmux(monkeypatch, keys="bind-key -T prefix c new-window\n")
    grove_window.warm()
    assert calls == ["list-keys"]

    calls = _tmux(monkeypatch, platform="linux")
    grove_window.warm()
    assert calls == []
