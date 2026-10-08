import subprocess
from types import SimpleNamespace

from lemonaid.places import workspace_purpose


def test_live_harnesses_map_to_panes_without_counting_helpers(monkeypatch):
    monkeypatch.setattr(
        workspace_purpose.windows,
        "query",
        lambda *args: [
            "%1\t/dev/ttys001",
            "%2\t/dev/ttys002",
            "%3\t/dev/ttys003",
            "%4\t/dev/ttys004",
        ],
    )
    monkeypatch.setattr(
        workspace_purpose.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="ttys001 /opt/bin/codex --no-daemon\n"
            "ttys002 claude\n"
            "ttys003 node /opt/bin/codex.js\n"
            "ttys004 node /opt/bin/build.js\n"
            "?? /opt/bin/codex app-server\n"
            "ttys004 /opt/bin/codex-code-mode-host\n"
        ),
    )
    assert workspace_purpose.lemon_panes("job") == {"%1", "%2", "%3"}


def test_process_probe_failure_is_not_an_empty_workspace(monkeypatch):
    monkeypatch.setattr(workspace_purpose.windows, "query", lambda *args: ["%1\t/dev/ttys001"])

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 5)

    monkeypatch.setattr(workspace_purpose.subprocess, "run", fail)
    assert workspace_purpose.lemon_panes("job") is None
