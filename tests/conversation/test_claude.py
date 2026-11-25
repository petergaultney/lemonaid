"""A Claude transcript read as a conversation: typed input is the user's, other input isn't."""

import json

from lemonaid.conversation import claude, entry


def _write(path, *records):
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def test_read_sorts_user_lemon_tool_and_other_input(tmp_path):
    transcript = tmp_path / "s.jsonl"
    _write(
        transcript,
        {
            "type": "user",
            "timestamp": "t1",
            "origin": {"kind": "human"},
            "message": {"content": "look at the deck"},
        },
        {
            "type": "assistant",
            "timestamp": "t2",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "Looking."},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls\n-la"}},
                ]
            },
        },
        {
            "type": "user",
            "timestamp": "t3",
            "message": {"content": [{"type": "tool_result", "content": "x"}]},
        },
        {
            "type": "user",
            "timestamp": "t4",
            "isMeta": True,  # as lemonaid's peer deliveries are
            "origin": {"kind": "peer", "name": "lemonaid", "body": "PR merged"},
            "message": {"content": "<wrapped>PR merged</wrapped>"},
        },
        {"type": "user", "isMeta": True, "message": {"content": "caveat"}},
        {"type": "custom-title", "title": "x"},
    )

    assert claude.read(transcript, 10) == [
        entry.Entry(entry.USER, "look at the deck", "t1"),
        entry.Entry(entry.LEMON, "Looking.", "t2"),
        entry.Entry(entry.TOOL, "Bash: ls -la", "t2"),
        entry.Entry(entry.OTHER, "PR merged", "t4", "lemonaid"),
    ]


def test_read_keeps_the_newest(tmp_path):
    transcript = tmp_path / "s.jsonl"
    _write(
        transcript,
        *(
            {"type": "user", "origin": {"kind": "human"}, "message": {"content": str(n)}}
            for n in range(5)
        ),
    )

    assert [each.text for each in claude.read(transcript, 2)] == ["3", "4"]


def test_a_missing_transcript_reads_as_empty(tmp_path):
    assert claude.read(tmp_path / "gone.jsonl", 10) == []
