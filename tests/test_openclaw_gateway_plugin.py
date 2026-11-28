"""Lemonaid's OpenClaw plugin, run by node against a stand-in for OpenClaw's plugin API."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lemonaid.openclaw import plugin_install

KEY = "agent:main:x"
_PLUGIN = Path(plugin_install.__file__).parent / "gateway_plugin" / "index.js"

# Registers the plugin with a stand-in API, runs each step's hook, and prints what the plugin
# handed lemonaid and what each hook returned. A step is [hook, event, context]; `code` makes
# the stand-in lemonaid exit with that code.
_HARNESS = """
import { register, finalText } from %(plugin)s;
const [ownEdits, steps, code] = JSON.parse(process.argv[2]);
const handlers = {};
const ran = [];
const run = async (event, payload) => {
  ran.push([event, payload]);
  return { code, stderr: code === 2 ? "refused\\n" : "" };
};
let clock = 0;
register({ on: (name, handler) => (handlers[name] = handler) }, { ownEdits }, run, () => clock);
const returned = [];
for (const [hook, event, ctx, at] of steps) {
  clock = at ?? clock;
  returned.push((await handlers[hook](event, ctx)) ?? null);
}
console.log(JSON.stringify({ ran, returned, final: finalText(steps[0][1].messages) }));
"""


def _run(tmp_path, steps: list, code: int = 0) -> dict:
    if shutil.which("node") is None:
        pytest.skip("node isn't installed")
    script = tmp_path / "harness.mjs"
    script.write_text(_HARNESS % {"plugin": json.dumps(_PLUGIN.as_uri())})
    done = subprocess.run(
        ["node", str(script), json.dumps([str(tmp_path / "own-edits"), steps, code])],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def test_a_turn_is_reported_when_it_starts_and_ends_with_what_the_lemon_said_last(tmp_path):
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "text", "text": "(quiet)"}]},
    ]
    found = _run(
        tmp_path,
        [
            [
                "agent_end",
                {"messages": messages, "success": True, "runId": "r1"},
                {"sessionKey": KEY},
                9000,
            ],
            ["llm_input", {"runId": "r2"}, {"sessionKey": KEY}, 10000],
        ],
    )

    assert found["final"] == "(quiet)"
    assert found["ran"] == [
        [
            "turn-end",
            {
                "session_key": KEY,
                "run": "r1",
                "at": 9,
                "said": "(quiet)",
                "failed": False,
                "error": "",
            },
        ],
        ["turn", {"session_key": KEY, "run": "r2", "at": 10}],
    ]


def test_a_failed_turn_is_reported_without_a_message(tmp_path):
    found = _run(
        tmp_path,
        [
            [
                "agent_end",
                {"messages": [], "success": False, "error": "rate limited"},
                {"sessionKey": KEY},
            ]
        ],
    )

    [(event, payload)] = found["ran"]
    assert (event, payload["failed"], payload["error"], payload["said"]) == (
        "turn-end",
        True,
        "rate limited",
        "",
    )


def test_a_running_turn_is_renewed_once_a_minute_from_its_tool_calls(tmp_path):
    steps = [
        ["llm_input", {"runId": "r1"}, {"sessionKey": KEY}, 0],
        ["after_tool_call", {"params": {}}, {"sessionKey": KEY}, 30000],
        ["after_tool_call", {"params": {}}, {"sessionKey": KEY}, 61000],
    ]

    assert [payload["at"] for _, payload in _run(tmp_path, steps)["ran"]] == [0, 61]


def test_a_tool_call_naming_no_watched_doc_starts_nothing(tmp_path):
    found = _run(
        tmp_path, [["before_tool_call", {"params": {"command": "ls"}}, {"sessionKey": KEY}]]
    )

    assert found == {"ran": [], "returned": [None], "final": ""}


def test_a_tool_call_naming_a_watched_doc_is_handed_to_lemonaid(tmp_path):
    writer = tmp_path / "own-edits" / f"openclaw-{KEY}"
    writer.mkdir(parents=True)
    (writer / "abc.doc").write_text("/srv/notes/plan.md")
    params = {"path": "/srv/notes/plan.md"}

    found = _run(
        tmp_path,
        [
            ["before_tool_call", {"params": params, "toolCallId": "c1"}, {"sessionKey": KEY}],
            [
                "after_tool_call",
                {"params": params, "toolCallId": "c1", "result": "ok"},
                {"sessionKey": KEY},
                1000,
            ],
        ],
    )

    tools = [payload for event, payload in found["ran"] if event == "tool"]
    assert [(t["hook_event_name"], t["tool_use_id"]) for t in tools] == [
        ("PreToolUse", "c1"),
        ("PostToolUse", "c1"),
    ]
    assert tools[1]["tool_response"] == "ok"


def test_a_push_lemonaid_refuses_is_blocked(tmp_path):
    found = _run(
        tmp_path,
        [["before_tool_call", {"params": {"command": "git push -q"}}, {"sessionKey": KEY}]],
        code=2,
    )

    assert found["returned"] == [{"block": True, "blockReason": "refused"}]
