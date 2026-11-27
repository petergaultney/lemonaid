import os
import pathlib
import subprocess
import sys


def skill(directory: pathlib.Path, name: str, body: str = "Do it.") -> None:
    path = directory / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {name} skill\n---\n\n{body}\n")


def configure(text: str) -> None:
    pathlib.Path(os.environ["LEMONAID_CONFIG"]).write_text(text)


def lemonaid_skills(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lemonaid", "skills", *args],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
