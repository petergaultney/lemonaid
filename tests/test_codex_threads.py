"""Codex answers which threads are gone; their rollout files answer when it can't."""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from uuid import UUID

import pytest

from lemonaid.codex import threads, utils

_ASK = threads._ask  # conftest stubs it for every other test

_LIVE = "01a1f3b9-8daa-76a1-baa0-9a9ce97ef69f"
_UNKNOWN = "01a0afc2-0344-77c2-b058-000000000000"
_NO_ROLLOUT = "019c2430-eae9-7560-aa54-c5582d4c81ec"
_ARCHIVED = "01a0afc2-0344-77c2-b058-81b023b7b5a4"
_ODD = "01a1c6eb-7681-7f12-a720-eaaf968d7ba2"  # Codex errors in a way it doesn't recognize

# A stand-in `codex app-server`: answers from the JSON in $FAKE_CODEX, two archived
# threads per `thread/list` page so the listing is paged.
_FAKE = """
import json, os, sys
plan = json.load(open(os.environ["FAKE_CODEX"]))
if plan.get("exit"):
    sys.exit(1)
if plan.get("deaf"):
    import time
    time.sleep(60)
archived = plan.get("archived", [])
for line in sys.stdin:
    message = json.loads(line)
    method, id = message["method"], message.get("id")
    if method == "initialized" or plan.get("hang"):
        continue
    if method == "initialize":
        result = {"userAgent": "fake"}
    elif method == "thread/list":
        start = int(message["params"]["cursor"] or 0)
        page = archived[start:start + 2]
        more = start + 2 < len(archived)
        result = {"data": [{"id": t} for t in page], "nextCursor": str(start + 2) if more else None}
    else:
        error = plan["errors"].get(message["params"]["threadId"])
        if error:
            print(json.dumps({"id": id, "error": {"code": -32600, "message": error}}), flush=True)
            continue
        result = {"data": [{}], "nextCursor": None}
    print(json.dumps({"method": "noise/elsewhere", "params": {}}), flush=True)
    print(json.dumps({"id": id, "result": result}), flush=True)
"""


@pytest.fixture
def codex(tmp_path, monkeypatch):
    """Put a fake `codex` on PATH, answering from the plan that the test passes in."""
    monkeypatch.setattr(threads, "_ask", _ASK)
    binary = tmp_path / "bin" / "codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\nimport sys; sys.argv[1:] = []\n{_FAKE}")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary.parent))
    monkeypatch.setattr(utils, "get_sessions_root", lambda: tmp_path / "sessions")

    def plan(**answers):
        (tmp_path / "plan.json").write_text(json.dumps({"errors": {}, **answers}))
        monkeypatch.setenv("FAKE_CODEX", str(tmp_path / "plan.json"))

    return plan


def _rollout(tmp_path, thread: str) -> None:
    day = datetime.fromtimestamp((UUID(thread).int >> 80) / 1000, UTC).date()
    directory = tmp_path / "sessions" / day.strftime("%Y/%m/%d")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"rollout-2026-01-01T00-00-00-{thread}.jsonl.zst").write_bytes(b"zstd")


def test_codex_decides_and_its_unrecognized_errors_fall_back_to_rollout_files(codex, tmp_path):
    codex(
        archived=["a", "b", "c", _ARCHIVED],
        errors={
            _UNKNOWN: f"thread not loaded: {_UNKNOWN}",
            _NO_ROLLOUT: f"invalid paginated history lineage for {_NO_ROLLOUT}: missing source rollout",
            _ODD: "database is locked",
        },
    )
    _rollout(tmp_path, _NO_ROLLOUT)  # Codex's answer wins over a file it can't use
    _rollout(tmp_path, _ODD)

    assert threads.gone([_LIVE, _UNKNOWN, _NO_ROLLOUT, _ARCHIVED, _ODD, ""]) == {
        _UNKNOWN,
        _NO_ROLLOUT,
        _ARCHIVED,
        "",
    }


@pytest.mark.parametrize("failure", [{"exit": True}, {"hang": True}, None])
def test_with_no_answer_from_codex_rollout_files_decide(codex, tmp_path, monkeypatch, failure):
    if failure is None:
        monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    else:
        codex(**failure)
    monkeypatch.setattr(threads, "_TIMEOUT", 0.5)
    _rollout(tmp_path, _LIVE)

    assert threads.gone([_LIVE, _UNKNOWN]) == {_UNKNOWN}


def test_a_codex_that_never_reads_its_input_cannot_outlast_the_deadline(
    codex, tmp_path, monkeypatch
):
    """Many more requests than a pipe holds, to a Codex that never reads one."""
    codex(deaf=True)
    monkeypatch.setattr(threads, "_TIMEOUT", 0.5)
    started: list[subprocess.Popen] = []
    popen = subprocess.Popen

    def recording(*args, **kwargs):
        started.append(popen(*args, **kwargs))
        return started[-1]

    monkeypatch.setattr(subprocess, "Popen", recording)
    batch = [f"01a1f3b9-8daa-76a1-baa0-{n:012x}" for n in range(5000)]

    begun = time.monotonic()
    assert threads.gone(batch) == set(batch)
    assert time.monotonic() - begun < 3
    assert [proc.returncode is not None for proc in started] == [True]
