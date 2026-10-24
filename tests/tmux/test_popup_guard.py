"""The popup guard on a real tmux server, with control-mode clients standing in for the terminal
a person types into and for the `tmux attach` inside a popup.
"""

import shutil
import subprocess
import time
import uuid

import pytest
from tests import tmux_hook_sync

from lemonaid.tmux import fast_popup, popup_guard

_SESSION = "_lma_grove"
_HOOKS = ("client-attached", "client-session-changed")


@pytest.fixture
def tmux(monkeypatch):
    """A server with the popup's session and two others, `home` and `away`, and the guard."""
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")

    name = f"lemonaid-test-{uuid.uuid4().hex[:8]}"

    def run(*args: str) -> subprocess.CompletedProcess:
        return tmux_hook_sync.run(name, *args)

    if run("-f", "/dev/null", "new-session", "-d", "-s", "home").returncode != 0:
        pytest.skip("cannot start tmux")

    tmux_hook_sync.install(name, _HOOKS)
    for session in (_SESSION, "away"):
        run("new-session", "-d", "-s", session)
    for hook, command in popup_guard.hooks(_SESSION, fast_popup.OPENER_OPTION).items():
        run("set-hook", "-g", hook, command).check_returncode()
    monkeypatch.setenv("TMUX", f"{run('display', '-p', '#{socket_path}').stdout.strip()},0,0")
    clients: list[subprocess.Popen] = []

    def names() -> set[str]:
        return set(run("list-clients", "-F", "#{client_name}").stdout.split())

    def attach(session: str) -> str:
        before = names()
        clients.append(
            subprocess.Popen(
                ["tmux", "-L", name, "-C", "attach", "-t", session],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        _until(lambda: names() - before)
        return (names() - before).pop()

    try:
        yield run, attach
    finally:
        for client in clients:
            client.kill()
        run("kill-server")


def _until(done) -> None:
    deadline = time.monotonic() + 5
    while not done():
        if time.monotonic() >= deadline:
            raise AssertionError("timed out")
        time.sleep(0.02)


def _sessions(run) -> dict[str, str]:
    rows = run("list-clients", "-F", "#{client_name}|#{session_name}").stdout.splitlines()
    return dict(row.split("|", 1) for row in rows)


def test_a_switch_in_the_popup_moves_its_opener_and_closes_it(tmux):
    run, attach = tmux
    opener = attach("home")
    popup = attach(_SESSION)
    run("set-option", "-t", f"={_SESSION}:", fast_popup.OPENER_OPTION, opener)
    run("switch-client", "-c", popup, "-t", "away")
    _until(lambda: _sessions(run).get(opener) == "away")
    _until(lambda: popup not in _sessions(run))


def test_another_client_switching_session_is_left_alone(tmux):
    run, attach = tmux
    opener = attach("home")
    attach(_SESSION)
    other = attach("home")
    run("set-option", "-t", f"={_SESSION}:", fast_popup.OPENER_OPTION, opener)
    run("switch-client", "-c", other, "-t", "away")
    time.sleep(0.3)
    assert _sessions(run)[other] == "away"
    assert _sessions(run)[opener] == "home"


def test_a_new_client_on_the_popups_old_tty_is_not_taken_for_it(tmux):
    run, attach = tmux
    opener = attach("home")
    newcomer = attach("home")
    run("set-option", "-t", f"={_SESSION}:", fast_popup.OPENER_OPTION, opener)
    run("set-option", "-g", f"@lemonaid_inner{_SESSION}", f"{newcomer}:1")  # a gone process
    run("switch-client", "-c", newcomer, "-t", "away")
    time.sleep(0.3)
    assert _sessions(run)[newcomer] == "away"
    assert _sessions(run)[opener] == "home"
