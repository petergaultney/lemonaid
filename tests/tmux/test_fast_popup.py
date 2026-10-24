import json
import subprocess

from lemonaid.tmux import fast_popup


def _fake(monkeypatch, client: str, running: str | None = None, attached: str = ""):
    """A tmux whose resident was started with *running* settings (None: no resident)."""
    calls: list[tuple[str, ...]] = []
    opened: list[list[str]] = []

    def tmux(*args: str) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        out, code = "", 0
        if args[0] == "display-message" and "-p" in args:
            out = client
        elif args[0] == "has-session":
            code = 0 if running is not None else 1
        elif args[0] == "show-option" and fast_popup.SETTINGS_OPTION in args:
            target = args[args.index("-t") + 1]
            out = (
                (running or "")
                if target
                in (fast_popup.session_for("grove"), f"={fast_popup.session_for('grove')}:")
                else ""
            )
        elif args[0] == "list-clients":
            out = attached
        return subprocess.CompletedProcess(args, code, out, "")

    monkeypatch.setattr(fast_popup, "_tmux", tmux)
    monkeypatch.setattr(fast_popup.subprocess, "Popen", lambda argv, **_: opened.append(argv))
    return calls, opened


def test_a_session_name_with_spaces_still_opens_the_popup(monkeypatch):
    _, opened = _fake(monkeypatch, "/dev/ttys1:160:50:review with spaces\n")
    fast_popup.show("grove", 1)
    assert len(opened) == 1
    assert opened[0][opened[0].index("-w") + 1] == "158"


def test_the_resident_starts_with_the_callers_database_and_state(monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", "/tmp/b.db")
    monkeypatch.setenv("LEMONAID_STATE_DIR", "/tmp/b-state")
    calls, _ = _fake(monkeypatch, "/dev/ttys1:160:50:work")
    fast_popup.show("grove", 3)
    (started,) = [c for c in calls if c[0] == "new-session"]
    assert "LEMONAID_DB=/tmp/b.db" in started and "LEMONAID_STATE_DIR=/tmp/b-state" in started


def test_a_resident_with_other_settings_is_restarted(monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", "/tmp/b.db")
    old = json.dumps({"LEMONAID_DB": "/tmp/a.db"})
    calls, _ = _fake(monkeypatch, "/dev/ttys1:160:50:work", running=old)
    fast_popup.show("grove", 3)
    names = [c[0] for c in calls]
    assert names.index("kill-session") < names.index("new-session")


def test_the_popup_attaches_to_the_resident_and_records_the_client_it_opened_over(monkeypatch):
    calls, opened = _fake(monkeypatch, "/dev/ttys1:160:50:work")
    fast_popup.show("grove", 3)
    (popup,) = opened
    assert popup[popup.index("-c") + 1] == "/dev/ttys1"
    assert popup[popup.index("-x") + 1] == "3" and popup[popup.index("-y") + 1] == "47"  # bottom
    assert popup[-3:-1] == ["sh", "-c"] and popup[-1].endswith("attach-session -t =_lma_grove")
    assert ("set-option", "-t", "=_lma_grove:", fast_popup.OPENER_OPTION, "/dev/ttys1") in calls
    assert ("detach-client", "-s", "=_lma_grove") in calls  # off any other client first


def test_showing_it_from_inside_the_popup_closes_it(monkeypatch):
    calls, opened = _fake(monkeypatch, "/dev/ttys9:156:44:_lma_grove")
    fast_popup.show("grove", 3)
    assert opened == []
    assert ("detach-client", "-s", "=_lma_grove") in calls


def test_a_resident_with_the_same_settings_is_reused(monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", "/tmp/a.db")
    same = fast_popup.stamp(fast_popup.settings())
    calls, opened = _fake(monkeypatch, "/dev/ttys1:160:50:work", running=same)
    fast_popup.show("grove", 3)
    assert len(opened) == 1
    assert not any(c[0] in ("kill-session", "new-session") for c in calls)


def test_settings_the_caller_left_unset_are_unset_for_the_resident(monkeypatch):
    monkeypatch.setenv("LEMONAID_DB", "/tmp/b.db")
    monkeypatch.delenv("LEMONAID_CONFIG", raising=False)
    calls, _ = _fake(monkeypatch, "/dev/ttys1:160:50:work")
    fast_popup.show("grove", 3)
    (started,) = [c for c in calls if c[0] == "new-session"]
    command = list(started)
    assert command[command.index("env") + 1 :].count("LEMONAID_CONFIG") == 1
    assert "LEMONAID_DB" not in command[command.index("env") :]


def test_warming_starts_a_missing_resident_without_opening_a_popup(monkeypatch):
    calls, opened = _fake(monkeypatch, "/dev/ttys1:160:50:work")
    fast_popup.warm("grove", 3)
    assert opened == []
    (started,) = [c for c in calls if c[0] == "new-session"]
    assert started[started.index("-x") + 1 : started.index("-y") + 2] == ("154", "-y", "44")


def test_a_resident_from_another_build_is_restarted(monkeypatch):
    older = json.dumps({"build": "0.1", "settings": fast_popup.settings()}, sort_keys=True)
    calls, _ = _fake(monkeypatch, "/dev/ttys1:160:50:work", running=older)
    fast_popup.warm("grove", 3)
    assert [c[0] for c in calls if c[0] in ("kill-session", "new-session")] == [
        "kill-session",
        "new-session",
    ]


def test_starting_the_resident_installs_the_hook_that_keeps_its_popup_on_it(monkeypatch):
    calls, _ = _fake(monkeypatch, "/dev/ttys1:160:50:main\n")
    fast_popup.warm("grove", 1)
    assert any(c[:3] == ("set-hook", "-g", "client-session-changed[110]") for c in calls)
