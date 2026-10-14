"""Watch every readable source, retaining the list across an incomplete brief write."""

import json
from pathlib import Path

from . import cursors, subscriptions


def reported(root: Path) -> set[str]:
    try:
        return set(json.loads((root / "brief-problems.json").read_text()))
    except (OSError, ValueError):
        return set()


def read(
    path: Path, root: Path, cwd: Path, owner: str = "", vaults: tuple[Path, ...] = ()
) -> tuple[list[subscriptions.Subscription], str]:
    saved = root / "subscriptions.md"
    text = path.read_text()
    if not text.strip() or not any(line.startswith("# ") for line in text.splitlines()):
        try:
            previous = saved.read_text()
        except FileNotFoundError:
            previous = ""
        specs = subscriptions.read(previous, cwd, owner, vaults)
        problems = [
            "Incomplete brief header; "
            + (
                "keeping the last readable list."
                if previous
                else "no saved list; still watching the inbox."
            )
        ]
    else:
        reading = subscriptions.report(text, cwd, owner, vaults)
        specs, problems = list(reading.specs), list(reading.problems)
        if not saved.exists() or saved.read_text() != text:
            cursors.write_text(saved, text)
    problems = [p.replace("\n", " ") for p in problems]
    seen = reported(root) & set(problems)
    cursors.write_json(root / "brief-problems.json", sorted(seen))
    new = [p for p in problems if p not in seen]
    message = (
        f"Invalid subscriptions in {path}:\n" + "\n".join(f"- {p}" for p in new) if new else ""
    )
    return specs, message


def remember(root: Path, problem: str) -> None:
    delivered = {line[2:] for line in problem.splitlines() if line.startswith("- ")}
    cursors.write_json(root / "brief-problems.json", sorted(reported(root) | delivered))
