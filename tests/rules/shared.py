"""A rule doc and pattern files built from it, for the `rules` tests."""

import json
from pathlib import Path

RULES = """# Rules

1. **Start a reviewer yourself** after opening a PR.
2. **Keep the Status true.**
   - It says what you wait on.

- **A PR ready to merge gets the merge Status.** Nothing else, and no question.
  The user merges from the Status.
- **Push your own branch.**
"""

MERGE_ASK = {
    "id": "merge-ask",
    "regex": r"(?i)\b(?:want me to|should i) merge\b|\bready to merge\?",
    "rule_file": "rules.md",
    "rule_starts": "- **A PR ready to merge",
    "mode": "report",
    "say": "Set the Status to merge and don't ask.",
    "match": ["Want me to merge it?", "CI is green. Ready to merge?"],
    "no_match": ["The user merged it.", "I resolved the merge conflict."],
}

REVIEWER_ASK = {
    "id": "reviewer-ask",
    "regex": r"(?i)\bstart (?:a|the) reviewer\?",
    "rule_file": "rules.md",
    "rule_starts": "1. **Start a reviewer",
    "mode": "report",
    "match": ["Should I start a reviewer?"],
    "no_match": ["I started a reviewer."],
}


def _table(fields: dict) -> str:
    return "\n".join(
        [
            "[[pattern]]",
            *(
                f"{key} = '''{value}'''" if key == "regex" else f"{key} = {json.dumps(value)}"
                for key, value in fields.items()
            ),
        ]
    )


def write(directory: Path, *patterns: dict, rules: str = RULES) -> Path:
    """A pattern file holding *patterns*, beside `rules.md` holding *rules*."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "rules.md").write_text(rules)
    path = directory / "patterns.toml"
    path.write_text("\n\n".join(_table(pattern) for pattern in patterns) + "\n")
    return path


def configure(config: Path, patterns: Path | None, report_to: str = "") -> None:
    config.write_text(
        "[rules]\n"
        + (f"patterns = {json.dumps(str(patterns))}\n" if patterns else "")
        + (f"report_to = {json.dumps(report_to)}\n" if report_to else "")
    )
