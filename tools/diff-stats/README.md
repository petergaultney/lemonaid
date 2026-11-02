# diff-stats

Categorizes a Git diff by file purpose, outputs a markdown table with line counts and percentages, and
lists files for each non-lockfile category.

File categories (first match wins):

- **lockfiles** — `*.lock`, `lock.json`
- **notebooks** — `*.ipynb`
- **CI** — `.github/**`
- **tests** — `*/tests/*`, `test_*`, `conftest*`
- **runtime-docs** — `*.md` under a `src/` segment (lemon tool docs, KB skills, instruction files: prose
  that ships with the package and affects runtime behavior, distinct from both repo docs and code)
- **docs** — `*.md`, `*/docs/*`, `docs/**`
- **config** — `*.toml`, `*.cfg`, `*.ini`, `*.json`, `Dockerfile*`, non-CI `*.yml`/`*.yaml`
- **scripts** — any path containing a `scripts/` segment (non-runtime tooling, benchmarks, etc.)
- **code** — everything else

Python files in the **code** category are split further by changed line:

- **code-comments**: comment-only lines; inline comments remain code
- **code-docstrings**: module, class, function, and async-function docstrings recognized by the Python
  AST
- **code**: all remaining changed lines, including blank and formatting-only lines so totals match Git

The pre-change and post-change files are parsed independently, so both additions and removals are
classified. A file can contribute lines to more than one of these three categories; the total file count
still counts it once. If either version is not valid Python, all changes for that file remain code and
the tool prints a warning.

The implementation uses a `src/diff_stats` package. The top-level `diff-stats.py` is a thin bootstrap so
CI and local callers can run the tool directly without installing it.

## Usage

```bash
# Compare current branch to main (default)
python3 tools/diff-stats/diff-stats.py

# Compare to a specific base
python3 tools/diff-stats/diff-stats.py origin/main

# Update a PR description with the diff breakdown
python3 tools/diff-stats/diff-stats.py --pr 3836
```

With `--pr`, the script finds and replaces an existing `<details>` diff breakdown section in the PR body
(matched by the `<b>Diff breakdown</b>` summary between `---` rules). If no existing section is found, it
inserts one before `## Test plan`. The PR section lists at most 30 files per category, so a large PR's
description stays small enough for CI to pass the GitHub event through an environment variable.

Pure stdlib Python (plus `gh` CLI for `--pr`) — no venv needed.

## When to use

- Writing or updating a PR description that includes diff size context
- When the user asks "how big is this diff?" or "what changed?"
- Any time lockfile churn dominates a diff and you want to quantify it

## Interpreting results

The table shows what fraction of the diff is lockfile reformatting vs actual code. Use the percentages
and code file count in PR descriptions, e.g.:

> **Diff size note**: the GitHub diff looks enormous but 98.7% is `uv` lockfile reformatting. Actual
> code/config/docs: 62 files, +773/-201 lines.

The code file listing helps verify nothing unexpected slipped in.
