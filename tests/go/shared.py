import argparse
import subprocess

import pytest

from lemonaid import go
from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db


def run(*words):
    parser = argparse.ArgumentParser()
    go.setup_parser(parser.add_subparsers())
    args = parser.parse_args(["go", *words])
    args.func(args)


@pytest.fixture
def target():
    path = store.briefs_dir() / "jump.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Jump\n")
    with db.connect() as conn:
        db.add(
            conn,
            "codex:jump",
            "",
            switch_source="tmux",
            metadata={
                "tty": "/dev/target",
                "tmux_socket": "/test/socket",
                "tmux_session": "work",
                "tmux_session_order": [100, 90, 2],
                "tmux_pane_identity": ["%7", 90],
            },
        )
        attached.attach(conn, "codex:jump", path)
        return identity.ensure(conn, path)


@pytest.fixture
def calls(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        outputs = {
            "list-panes": "%7|/dev/target|work|100|90|$2\n",
            "list-clients": "/dev/client|source\n",
            "display-message": "source\n",
            "switch-client": "",
        }
        assert argv[:3] == ["tmux", "-S", "/test/socket"]
        return subprocess.CompletedProcess(argv, 0, stdout=outputs[argv[3]])

    monkeypatch.setattr(go.subprocess, "run", run)
    return calls
