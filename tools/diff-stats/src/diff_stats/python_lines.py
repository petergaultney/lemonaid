"""Classify changed Python lines as code, comments, or docstrings."""

import ast
import io
import tokenize
from collections import abc

from . import git_diff

_TRIVIA_TOKENS = {
    tokenize.ENCODING,
    tokenize.ENDMARKER,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.NEWLINE,
    tokenize.NL,
}


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue

        first = node.body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            continue

        lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))

    return lines


def _line_categories(source: bytes) -> dict[int, str]:
    """Keep formatting-only lines in code so the categories remain lossless."""
    docstring_lines = _docstring_lines(ast.parse(source))
    comment_lines: set[int] = set()
    code_lines: set[int] = set()

    for token in tokenize.tokenize(io.BytesIO(source).readline):
        if token.type == tokenize.COMMENT:
            comment_lines.add(token.start[0])
        # Multi-line tokens keep non-docstring strings and continuations in code.
        elif token.type not in _TRIVIA_TOKENS:
            code_lines.update(range(token.start[0], token.end[0] + 1))

    return {
        line: (
            "code-docstrings"
            if line in docstring_lines
            else "code-comments"
            if line in comment_lines and line not in code_lines
            else "code"
        )
        for line in docstring_lines | comment_lines | code_lines
    }


def classify_changed_lines(
    before: bytes,
    after: bytes,
    removed_lines: set[int],
    added_lines: set[int],
) -> dict[str, tuple[int, int]]:
    before_categories = _line_categories(before) if removed_lines else {}
    after_categories = _line_categories(after) if added_lines else {}
    counts = {name: [0, 0] for name in ("code", "code-comments", "code-docstrings")}

    for line in removed_lines:
        counts[before_categories.get(line, "code")][1] += 1
    for line in added_lines:
        counts[after_categories.get(line, "code")][0] += 1

    return {name: (added, removed) for name, (added, removed) in counts.items()}


def classify_python_diff(
    base: str,
    expected_counts: abc.Mapping[str, tuple[int, int]],
) -> tuple[dict[str, dict[str, tuple[int, int]]], list[str]]:
    source_changes, warnings = git_diff.changed_python_sources(base, expected_counts)
    classifications: dict[str, dict[str, tuple[int, int]]] = {}

    for path, change in source_changes.items():
        try:
            counts = classify_changed_lines(
                change.before,
                change.after,
                change.removed_lines,
                change.added_lines,
            )
        except (SyntaxError, tokenize.TokenError, UnicodeDecodeError, LookupError) as exc:
            warnings.append(f"could not parse Python source for {path!r}: {exc}")
            continue

        actual = (
            sum(added for added, _ in counts.values()),
            sum(removed for _, removed in counts.values()),
        )
        if actual != expected_counts[path]:
            warnings.append(
                f"Python line counts did not match numstat for {path!r}: "
                f"{actual!r} != {expected_counts[path]!r}"
            )
            continue

        classifications[path] = counts

    return classifications, warnings
