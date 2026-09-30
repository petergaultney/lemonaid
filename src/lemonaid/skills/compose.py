"""A packaged skill's installed text: the packaged SKILL.md plus one optional user file.

The user file lives in `<user dir>/<name>/`, by default `~/.lemons/skills/<name>/`, and is
exactly one of `overlay.md`, appended after the packaged body, or `SKILL.md`, used instead
of it. There is no merge language: changing a packaged paragraph means replacing the
whole skill, which then stops following packaged updates.
"""

import pathlib
import typing as ty

from ..home import layout

PACKAGED_DIR = pathlib.Path(__file__).parent / "packaged"


class Problem(Exception):
    pass


class Rendered(ty.NamedTuple):
    name: str
    text: str
    source: str  # "packaged", "packaged + <overlay>", or "<replacement> (replaces packaged)"


def default_user_dir() -> pathlib.Path:
    return layout.lemons_dir() / "skills"


def packaged_names(packaged_dir: pathlib.Path) -> list[str]:
    return sorted(p.parent.name for p in packaged_dir.glob("*/SKILL.md"))


def render(packaged_dir: pathlib.Path, user_dir: pathlib.Path, name: str) -> Rendered:
    packaged = packaged_dir / name / "SKILL.md"
    if not packaged.is_file():
        raise Problem(
            f"no packaged skill {name!r}; packaged: {', '.join(packaged_names(packaged_dir))}"
        )

    overlay, replacement = user_dir / name / "overlay.md", user_dir / name / "SKILL.md"
    if overlay.exists() and replacement.exists():
        raise Problem(f"{overlay.parent} has both overlay.md and SKILL.md; keep one")

    if replacement.exists():
        return Rendered(name, replacement.read_text(), f"{replacement} (replaces packaged)")

    if not overlay.exists():
        return Rendered(name, packaged.read_text(), "packaged")

    added = overlay.read_text()
    if added.startswith("---\n"):
        raise Problem(
            f"{overlay} starts with frontmatter; an overlay only adds sections, so replace "
            "the whole skill with SKILL.md to change the frontmatter"
        )

    return Rendered(
        name, f"{packaged.read_text().rstrip()}\n\n{added.strip()}\n", f"packaged + {overlay}"
    )
