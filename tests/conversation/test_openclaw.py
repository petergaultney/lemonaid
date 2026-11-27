"""An OpenClaw session read through the gateway's `chat.history`."""

import json
import stat

import pytest

from lemonaid.conversation import entry, openclaw
from lemonaid.openclaw import turns

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

    found = openclaw.read(KEY, _cli(tmp_path, {"messages": messages}), 10, str)

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

    found = openclaw.read(KEY, _paged_cli(tmp_path, [newest, older]), 2, str)

    assert [(each.role, each.text) for each in found] == [
        (entry.LEMON, "second"),
        (entry.TOOL, "exec: ls"),
        (entry.TOOL, "exec: make"),
        (entry.LEMON, "third"),
    ]


def test_a_spawned_session_starts_with_its_spawners_task(tmp_path):
    messages = [
        {"role": "user", "content": "[Subagent Task] check the pump", "__openclaw": {"seq": 1}},
        {"role": "user", "content": "how is it going?", "__openclaw": {"seq": 7}},
    ]
    answer = {"messages": messages, "sessionInfo": {"spawnedBy": "agent:main:matrix:room"}}

    found = openclaw.read(KEY, _cli(tmp_path, answer), 10, {"agent:main:matrix:room": "Meyer"}.get)

    assert [(each.role, each.sender) for each in found] == [
        (entry.OTHER, "Meyer"),
        (entry.USER, ""),
    ]


def test_read_raises_oserror_when_the_gateway_fails(tmp_path):
    with pytest.raises(OSError):
        openclaw.read(KEY, _cli(tmp_path, {}, code=1), 10, str)


def test_a_failed_turn_shows_where_it_falls_in_the_conversation():
    key = "agent:main:matrix:channel:!failing"
    said = [
        entry.Entry(entry.USER, "you didn't fix it", "2026-11-26T05:41:31.937000+00:00"),
        entry.Entry(entry.LEMON, "fixed now", "2026-11-26T05:48:00+00:00"),
    ]
    for at_ms in (1795600000000, 1795671692929):  # before the conversation shown, then after "you"
        turns.note(
            {
                "runId": str(at_ms),
                "stream": "lifecycle",
                "ts": at_ms,
                "sessionKey": key,
                "data": {"phase": "error", "error": "Auth profile unavailable"},
            }
        )

    shown = openclaw.with_failures(said, key)

    assert [each.role for each in shown] == [entry.USER, entry.FAILED, entry.LEMON]
    assert shown[1].text == "Auth profile unavailable"


def test_a_message_shows_the_files_sent_with_it_even_with_no_text(tmp_path):
    media = [
        {"fileName": "photo.png", "sizeBytes": 2048, "contentType": "image/png"},
        {"fileName": "notes.txt", "sizeBytes": 26, "contentType": "text/plain"},
    ]
    messages = [
        {
            "role": "user",
            "content": "look",
            "timestamp": "1795622032553",
            "__openclaw": {"media": media},
        },
        {
            "role": "user",
            "content": "",
            "timestamp": "1795622032553",
            "__openclaw": {"media": media[:1]},
        },
    ]

    found = openclaw.read(KEY, _cli(tmp_path, {"messages": messages}), 10, str)

    assert [(each.text, each.files) for each in found] == [
        ("look", (("photo.png", 2048), ("notes.txt", 26))),
        ("", (("photo.png", 2048),)),
    ]
