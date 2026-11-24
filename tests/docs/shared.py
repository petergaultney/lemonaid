import os
from pathlib import Path

import yaml


def doc(root: Path, name: str, fields: dict | None = None, body: str = "Body.\n") -> Path:
    """A Markdown file under *root* with *fields* as its frontmatter."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    front = f"---\n{yaml.safe_dump(fields, sort_keys=False)}---\n" if fields is not None else ""
    path.write_text(front + body)
    return path


def configure(roots: list[Path], extra: str = "") -> None:
    """Point the test's lemonaid config at *roots*."""
    listed = ", ".join(f'"{root}"' for root in roots)
    Path(os.environ["LEMONAID_CONFIG"]).write_text(f"[docs]\nroots = [{listed}]\n{extra}")
