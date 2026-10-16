from lemonaid.tmux import scratch, scratch_autosave
from tests.test_follow_hook import _followed_pane


def start(tmux, monkeypatch):
    pane = _followed_pane(tmux)
    scratch.set_follow_enabled(True)
    scratch.set_position("left")
    scratch._save_size("left", "58")
    scratch._save_size("top", "12")
    scratch_autosave.install_guards()
    monkeypatch.setenv("TMUX_PANE", pane)
    tmux("select-window", "-t", "a:w2")
    observer = scratch_autosave.Observer()
    observer.poll(0)
    assert scratch_autosave._sample(pane) is not None
    return pane, observer


def settle(observer, now=1):
    observer.poll(now)
    observer.poll(now + 1)
