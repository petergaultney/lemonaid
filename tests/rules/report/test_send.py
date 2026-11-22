import subprocess
import sys

from lemonaid.rules import report, snapshot


def test_send_starts_tell_detached_with_the_lemon_as_sender(monkeypatch):
    started = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda argv, **options: started.append((argv, options))
    )

    report.send("rules-desk", "codex:abc", "--looks like a flag")

    [(argv, options)] = started
    assert argv == [
        sys.executable,
        "-m",
        "lemonaid",
        "tell",
        "--channel",
        "codex:abc",
        "--",
        "rules-desk",
        "--looks like a flag",
    ]
    assert options["start_new_session"] is True
    assert (snapshot.rules_dir() / "tell.log").exists()
