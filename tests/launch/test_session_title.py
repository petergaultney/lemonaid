from pathlib import Path

import pytest

from lemonaid.launch import handoff


def _given(tmp_path: Path, text: str, name: str = "") -> handoff.Handoff:
    path = tmp_path / "b.md"
    path.write_text(text)
    return handoff.Handoff(path, name=name)


@pytest.mark.parametrize(
    "heading, title",
    [
        ("# Output-doc brief", "Output-doc"),
        ("# Lemonaid next research Brief.", "Lemonaid next research"),
        ("# Pass the name to Claude and Codex", "Pass the name to Claude and Codex"),
        ("# Task: review brief", "Task: review"),
        ("# briefly", "briefly"),
    ],
)
def test_the_title_is_the_first_heading_without_a_trailing_brief(tmp_path, heading, title):
    assert handoff.session_title(_given(tmp_path, f"{heading}\n\nBody\n")) == title


def test_a_name_wins_over_the_heading(tmp_path):
    assert handoff.session_title(_given(tmp_path, "# Heading\n", name="Chosen")) == "Chosen"


def test_the_default_prompt_leads_with_the_title(tmp_path):
    given = _given(tmp_path, "# Heading\n", name="Chosen")

    assert (
        handoff.first_prompt(given, "")
        == f"Chosen. Your task file is {given.brief}; read it all and do the work."
    )
