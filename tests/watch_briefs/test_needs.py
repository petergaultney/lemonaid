import pytest

from lemonaid.watch import needs_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("### Needs Peter\n\n- first\n  line\n- second\n### Next\n- ignore", "first line second"),
        (
            "- **Needs Peter:** first\n\n  continuation\n  - second\n- Next: ignore",
            "first continuation second",
        ),
        ("### **Needs you**\n* first\n### Unknown\nignore", "first"),
        ("### Needs\nnone.", ""),
        ("- Needs Peter: no", ""),
        ("```md\n### Needs Peter\n- fake\n```\n### Needs Peter\n- real", "real"),
        ("### Needs Peter\n```sh\n# part of ask\n```\n### Next\nignore", "```sh # part of ask ```"),
        ("### Needs Peter\n~~~md\n# part of ask\n~~~\n### Next\nignore", "~~~md # part of ask ~~~"),
    ],
)
def test_needs_parsing(text, expected):
    assert needs_text.needs(text) == expected
