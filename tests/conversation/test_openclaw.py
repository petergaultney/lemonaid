"""An OpenClaw session read through the gateway's `chat.history`."""

import json
import stat

import pytest

from lemonaid.conversation import entry, openclaw

KEY = "agent:main:signal:direct:uuid:abc"


def _cli(tmp_path, answer: dict, code: int = 0) -> str:
    cli = tmp_path / "openclaw"
    cli.write_text(
        f"#!/usr/bin/env python3\nimport sys\nprint({json.dumps(json.dumps(answer))})\nsys.exit({code})\n"
    )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return str(cli)


def test_read_marks_input_from_someone_other_than_the_owner(tmp_path):
    messages = [
        {
            "role": "user",
            "content": "mail from HQ",
            "timestamp": "1795622032553",
            "__openclaw": {"senderIsOwner": False},
        },
        {"role": "user", "content": "how warm is it?", "timestamp": "1795622032553"},
        {
            "role": "user",
            "content": "from my phone",
            "timestamp": "1795622032553",
            "__openclaw": {
                "senderIsOwner": False,
                "senderName": "Sam",
                "transport": {"channel": "signal"},
            },
        },
        {
            "role": "assistant",
            "content": [
                {"type": "toolCall", "name": "bash", "arguments": {"command": "ha state"}},
                {"type": "text", "text": "68F inside."},
            ],
            "timestamp": "1795622032553",
        },
        {"role": "toolResult", "content": [{"type": "text", "text": "{}"}]},
    ]

    found = openclaw.read(KEY, _cli(tmp_path, {"messages": messages}), 10)

    assert [(each.role, each.text, each.sender) for each in found][:3] == [
        (entry.OTHER, "mail from HQ", "mail"),
        (entry.USER, "how warm is it?", ""),
        (entry.OTHER, "from my phone", "Sam \u00b7 Signal"),
    ]
    assert [(each.role, each.text) for each in found][3:] == [
        (entry.TOOL, "bash: ha state"),
        (entry.LEMON, "68F inside."),
    ]
    assert found[0].at.startswith("2026-11-25T")


def _paged_cli(tmp_path, pages: list[list[dict]]) -> str:
    """A CLI that answers `chat.history` a page at a time, the newest page first."""
    cli = tmp_path / "openclaw"
    cli.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        f"pages = json.loads({json.dumps(json.dumps(pages))})\n"
        'given = json.loads(sys.argv[sys.argv.index("--params") + 1])\n'
        'at = given["offset"] // given["limit"]\n'
        'print(json.dumps({"messages": pages[at], "hasMore": at + 1 < len(pages)}))\n'
    )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return str(cli)


def _said(text: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def _ran(command: str) -> list[dict]:
    call = {"type": "toolCall", "name": "exec", "arguments": {"command": command}}
    return [{"role": "assistant", "content": [call]}, {"role": "toolResult", "content": []}]


def test_read_goes_back_past_a_page_of_tool_calls_for_the_newest_messages(tmp_path):
    older = [_said("first"), _said("second"), *_ran("ls")]
    newest = [*_ran("make"), _said("third")]

    found = openclaw.read(KEY, _paged_cli(tmp_path, [newest, older]), 2)

    assert [(each.role, each.text) for each in found] == [
        (entry.LEMON, "second"),
        (entry.TOOL, "exec: ls"),
        (entry.TOOL, "exec: make"),
        (entry.LEMON, "third"),
    ]


def test_read_raises_oserror_when_the_gateway_fails(tmp_path):
    with pytest.raises(OSError):
        openclaw.read(KEY, _cli(tmp_path, {}, code=1), 10)
