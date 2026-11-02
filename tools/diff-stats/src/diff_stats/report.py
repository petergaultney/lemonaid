"""Format collected diff-stats categories as a report or PR description section."""

import json
import os
import re
import subprocess
import sys
import tempfile

# most interesting first, lockfiles last
CAT_NAMES = [
    "code",
    "code-comments",
    "code-docstrings",
    "scripts",
    "config",
    "runtime-docs",
    "docs",
    "CI",
    "tests",
    "notebooks",
    "lockfiles",
]

# CI passes the whole GitHub event, PR description included, through one environment variable,
# and Linux caps a single environment string at 128 KiB; listing every file of a large PR breaks CI.
_PR_FILES_PER_CATEGORY = 30

_PR_SECTION_RE = re.compile(
    r"<details><summary><b>Diff breakdown</b>.*?</details>",
    re.DOTALL,
)


def _fmt_pct_summary(pct: float) -> str:
    if pct >= 1:
        return f"{pct:.0f}%"

    if pct >= 0.05:
        return f"{pct:.1f}%"

    return "<0.1%"


def _summary_label(cats: dict[str, dict]) -> str:
    total = sum(c["added"] + c["removed"] for c in cats.values())
    if not total:
        return "no changes"

    return ", ".join(
        f"{_fmt_pct_summary((cats[n]['added'] + cats[n]['removed']) / total * 100)} {n}"
        for n in CAT_NAMES
        if cats[n]["files"]
    )


def _table_lines(cats: dict[str, dict]) -> list[str]:
    total = sum(c["added"] + c["removed"] for c in cats.values())
    lines = [
        "| Category | Files | +Lines | -Lines | Net | Total | % of diff |",
        "|----------|------:|-------:|-------:|----:|------:|----------:|",
    ]
    for name in CAT_NAMES:
        cat = cats[name]
        if not cat["files"]:
            continue

        net = cat["added"] - cat["removed"]
        pct = (cat["added"] + cat["removed"]) / total * 100 if total else 0
        lines.append(
            f"| {name} | {len(cat['files'])} | +{cat['added']} | -{cat['removed']}"
            f" | {net:+d} | {cat['added'] + cat['removed']} | {pct:.1f}% |"
        )
    return lines


def format_report(cats: dict[str, dict], base: str) -> str:
    total_added = sum(c["added"] for c in cats.values())
    total_removed = sum(c["removed"] for c in cats.values())
    total_files = len({filepath for cat in cats.values() for filepath in cat["files"]})

    lines = [
        f"## Diff stats: HEAD vs {base}",
        "",
        f"**Total**: {total_files} files, +{total_added}/-{total_removed}"
        f" ({total_added + total_removed} lines changed)",
        "",
        *_table_lines(cats),
    ]
    for name in CAT_NAMES:
        if name == "lockfiles":
            continue

        files = sorted(cats[name]["files"])
        if not files:
            continue

        c = cats[name]
        lines.extend(["", f"### {name} ({len(files)} files, +{c['added']}/-{c['removed']})"])
        lines.extend(f"  {f}" for f in files)

    return "\n".join(lines)


def format_pr_section(cats: dict[str, dict]) -> str:
    lines = [
        f"<details><summary><b>Diff breakdown</b> — {_summary_label(cats)}</summary>",
        "",
        *_table_lines(cats),
    ]
    for name in CAT_NAMES:
        if name == "lockfiles":
            continue

        files = sorted(cats[name]["files"])
        if not files:
            continue

        c = cats[name]
        n = len(files)
        lines.extend(
            [
                "",
                f"**{name}** ({n} file{'s' if n != 1 else ''}, +{c['added']}/-{c['removed']}):",
                ", ".join(f"`{f}`" for f in files[:_PR_FILES_PER_CATEGORY])
                + (f", and {n - _PR_FILES_PER_CATEGORY} more" if n > _PR_FILES_PER_CATEGORY else ""),
            ]
        )

    lines.extend(["", "</details>"])
    return "\n".join(lines)


def update_pr(pr_number: int, section: str) -> None:
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "body", "--jq", ".body"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"gh pr view failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    body = result.stdout.rstrip("\n")
    match = _PR_SECTION_RE.search(body)
    if match:
        body = body[: match.start()] + section + body[match.end() :]
    else:
        body = body + "\n\n---\n" + section

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(body)
        tmp = f.name

    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                "-X",
                "PATCH",
                f"repos/{{owner}}/{{repo}}/pulls/{pr_number}",
                "-F",
                f"body=@{tmp}",
            ],
            capture_output=True,
            text=True,
        )
    finally:
        os.unlink(tmp)

    if result.returncode != 0:
        print(f"gh api failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    print(f"Updated {json.loads(result.stdout).get('html_url', f'PR #{pr_number}')}")
