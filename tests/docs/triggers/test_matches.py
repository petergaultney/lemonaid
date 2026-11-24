from pathlib import Path

import pytest

from lemonaid.docs import triggers
from lemonaid.docs.frontmatter import Trigger


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --draft",
        "cd ~/src/app && gh pr create",
        "GH_HOST=example.com gh pr create",
        "git push -u origin topic; gh pr create --fill",
        "echo start\ngh pr create",
    ],
)
def test_a_command_regex_matches_each_simple_command(command):
    assert triggers.matches(
        Trigger("command", r"^gh pr create\b"), triggers.Action(commands=(command,))
    )


def test_a_command_regex_does_not_match_inside_another_command():
    action = triggers.Action(commands=("echo 'gh pr create'",))

    assert not triggers.matches(Trigger("command", r"^gh pr create\b"), action)


@pytest.mark.parametrize(
    ("pattern", "path", "matched"),
    [
        ("*.py", "/src/app/main.py", True),
        ("*.py", "/src/app/main.pyc", False),
        ("tests/**/*.py", "/src/app/tests/unit/test_x.py", True),
        ("tests/**/*.py", "/src/app/tests/test_x.py", True),
        ("/src/*.md", "/src/notes/a.md", False),
        ("/src/**", "/src/notes/a.md", True),
        ("~/notes/*.md", f"{Path.home()}/notes/a.md", True),
    ],
)
def test_an_edit_glob(pattern, path, matched):
    action = triggers.Action(written=(Path(path),))

    assert triggers.matches(Trigger("edit", pattern), action) is matched


def test_create_matches_only_new_files():
    trigger = Trigger("create", "*.md")

    assert triggers.matches(trigger, triggers.Action(created=(Path("/n/new.md"),)))
    assert not triggers.matches(trigger, triggers.Action(written=(Path("/n/old.md"),)))


def test_a_prompt_regex_is_searched_in_the_user_s_message():
    trigger = Trigger("prompt", "(?i)\\bmerge\\b")

    assert triggers.matches(trigger, triggers.Action(prompt="Please Merge it"))
    assert not triggers.matches(trigger, triggers.Action(commands=("git merge",)))
