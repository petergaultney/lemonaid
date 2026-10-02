"""`arrange serve` answers each snapshot with its file's arrange(), reloaded when the file changes."""

import io
import json
import os

from lemonaid.inbox.arrange import serve


def _write(path, body: str, mtime_ns: int) -> None:
    path.write_text(body)
    os.utime(path, ns=(mtime_ns, mtime_ns))


def _answers(path, *edits: str, same_mtime: bool = False) -> list[dict]:
    """One snapshot per entry of *edits*, each written to *path* just before its snapshot is read."""

    def lines():
        for i, body in enumerate(edits):
            _write(path, body, 10**9 if same_mtime else (i + 1) * 10**9)
            yield json.dumps({"n": i}) + "\n"

    out = io.StringIO()
    serve.serve(serve.reloading(path), lines(), out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_an_edit_takes_effect_at_the_next_snapshot(tmp_path):
    path = tmp_path / "arranger.py"

    answers = _answers(
        path,
        "def arrange(s):\n    return {'fold_label': 'one'}\n",
        "def arrange(s):\n    return {'fold_label': 'two'}\n",
    )

    assert answers == [{"fold_label": "one"}, {"fold_label": "two"}]


def test_a_broken_file_is_answered_as_an_error_until_it_is_fixed(tmp_path):
    path = tmp_path / "arranger.py"

    answers = _answers(
        path,
        "def arrange(s)\n",
        "x = 1\n",
        "def arrange(s):\n    return {}\n",
    )

    assert answers[0]["error"].startswith("SyntaxError")
    assert answers[1] == {"error": f"NoArrange: {path} defines no function arrange(snapshot)"}
    assert answers[2] == {}


def test_a_replacement_with_the_same_mtime_is_still_reloaded(tmp_path):
    path = tmp_path / "arranger.py"

    answers = _answers(
        path,
        "def arrange(s):\n    return {'fold_label': 'old'}\n",
        "def arrange(s):\n    return {'fold_label': 'new'}\n",
        same_mtime=True,
    )

    assert answers == [{"fold_label": "old"}, {"fold_label": "new"}]
