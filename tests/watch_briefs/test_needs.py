import pytest

from lemonaid.watch import briefs_events


@pytest.mark.parametrize(
    "text, expected",
    [
        ("### Needs you\n\n- first\n  line\n- second\n### Next\n- ignore", "first line second"),
        (
            "- **Needs you:** first\n\n  continuation\n  - second\n- Next: ignore",
            "first continuation second",
        ),
        ("### **Needs you**\n* first\n### Unknown\nignore", "first"),
        ("### Needs\nnone.", ""),
        ("- Needs you: no", ""),
        ("```md\n### Needs you\n- fake\n```\n### Needs you\n- real", "real"),
        ("### Needs you\n```sh\n# part of ask\n```\n### Next\nignore", "```sh # part of ask ```"),
        ("### Needs you\n~~~md\n# part of ask\n~~~\n### Next\nignore", "~~~md # part of ask ~~~"),
    ],
)
def test_needs_parsing(text, expected):
    assert briefs_events._needs(text) == expected
