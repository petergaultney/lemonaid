import dataclasses
import json

import pytest

from lemonaid.inbox import db
from lemonaid.launch.restart import startup, state

from .. import shared


@pytest.mark.parametrize("mismatch", ["token", "session", "model", "watcher", "generation"])
def test_readiness_requires_token_session_model_watcher_and_process(
    tmp_path, monkeypatch, mismatch
):
    with db.connect() as conn:
        shared.setup(conn, tmp_path)
        token = state.reserve(conn, shared.plan(tmp_path))
        replacement = dataclasses.replace(shared.TARGET, pid=999)
        state.update(conn, token, "verifying", replacement=dataclasses.asdict(replacement))
        conn.execute(
            "UPDATE harness_generations SET token = ?, session_id = ?, settings = ?",
            (
                "old" if mismatch == "token" else token,
                "other" if mismatch == "session" else shared.SESSION,
                json.dumps(
                    {**shared.SETTINGS, "model": "other"}
                    if mismatch == "model"
                    else shared.SETTINGS
                ),
            ),
        )
        conn.commit()
        monkeypatch.setattr(startup.pane, "check", lambda target: target)
        monkeypatch.setattr(startup.pane, "model", lambda *args: None)
        monkeypatch.setattr(startup.process, "same", lambda source: mismatch != "generation")
        monkeypatch.setattr(
            startup.process, "ancestry", lambda pid: [dataclasses.replace(shared.SOURCE, pid=999)]
        )
        monkeypatch.setattr(startup.watchers, "ready", lambda *args: mismatch != "watcher")
        assert not startup.ready(conn, state.get(conn, token))
