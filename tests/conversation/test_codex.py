"""A Codex rollout read as a conversation, from its completed items."""

import json

from lemonaid.conversation import codex, entry


def _item(item: dict, at: str = "t") -> dict:
    return {
        "timestamp": at,
        "type": "event_msg",
        "payload": {"type": "item_completed", "item": item},
    }


def test_read_takes_messages_and_commands(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    records = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "# AGENTS.md"}],
            },
        },
        _started("user"),
        _item({"type": "UserMessage", "content": [{"type": "text", "text": "review it"}]}, "t1"),
        _item({"type": "Reasoning", "summary_text": []}),
        _item({"type": "CommandExecution", "command": "cat README.md"}, "t2"),
        _item({"type": "AgentMessage", "content": [{"type": "Text", "text": "Done."}]}, "t3"),
    ]
    rollout.write_text("".join(json.dumps(record) + "\n" for record in records))

    assert codex.read(rollout, 10) == [
        entry.Entry(entry.USER, "review it", "t1"),
        entry.Entry(entry.TOOL, "exec: cat README.md", "t2"),
        entry.Entry(entry.LEMON, "Done.", "t3"),
    ]


def _started(trigger: str) -> dict:
    return {
        "type": "event_msg",
        "payload": {"type": "task_started", "turn_attribution": {"turn_trigger": trigger}},
    }


def _said(text: str) -> dict:
    return _item({"type": "UserMessage", "content": [{"type": "text", "text": text}]})


def test_a_queued_turns_first_message_is_not_the_users(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    records = [
        _started("queue"),
        _said("lemonaid message: mail from HQ"),
        _said("and stop after that"),
        _started("user"),
        _said("carry on"),
    ]
    rollout.write_text("".join(json.dumps(record) + "\n" for record in records))

    assert [(each.role, each.text) for each in codex.read(rollout, 10)] == [
        (entry.OTHER, "lemonaid message: mail from HQ"),
        (entry.USER, "and stop after that"),
        (entry.USER, "carry on"),
    ]


def test_a_message_whose_turn_start_wasnt_read_is_not_called_the_users(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    records = [
        _said("lemonaid message: mail from HQ"),
        _said("then this"),
        _started("user"),
        _said("go"),
    ]
    rollout.write_text("".join(json.dumps(record) + "\n" for record in records))

    assert [(each.role, each.sender) for each in codex.read(rollout, 10)] == [
        (entry.OTHER, ""),
        (entry.USER, ""),
        (entry.USER, ""),
    ]
