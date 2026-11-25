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


def test_read_raises_oserror_when_the_gateway_fails(tmp_path):
    with pytest.raises(OSError):
        openclaw.read(KEY, _cli(tmp_path, {}, code=1), 10)
