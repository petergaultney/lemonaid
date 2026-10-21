"""A packaged skill's installed text: the packaged SKILL.md plus one optional user file.

The user file lives in `<user dir>/<name>/`, by default `~/.lemons/skills/<name>/`, and is
exactly one of `overlay.md`, appended after the packaged body, or `SKILL.md`, used instead
of it. There is no merge language: changing a packaged paragraph means replacing the
whole skill, which then stops following packaged updates.

A packaged skill (or overlay) can address one harness with a section between a
`<!-- harness: claude -->` line and a `<!-- /harness -->` line. Each harness's copy keeps
its own sections and drops the others'.
"""

import pathlib
import re
import typing as ty

from ..home import layout

PACKAGED_DIR = pathlib.Path(__file__).parent / "packaged"


class Problem(Exception):
    pass


class Rendered(ty.NamedTuple):
    name: str
    text: str
    source: str  # "packaged", "packaged + <overlay>", or "<replacement> (replaces packaged)"


_SECTION = re.compile(
    r"^<!-- harness: (?P<harness>\w+) -->\n(?P<body>.*?)^<!-- /harness -->\n?", re.M | re.S
)


HARNESSES = ("claude", "codex")


def for_harness(text: str, harness: str) -> str:
    def keep(m: re.Match[str]) -> str:
        if m["harness"] not in HARNESSES:
            raise Problem(f"unknown harness {m['harness']!r} in a section marker")

        return m["body"] if m["harness"] == harness else ""

    return _SECTION.sub(keep, text)


def default_user_dir() -> pathlib.Path:
    return layout.lemons_dir() / "skills"


def packaged_names(packaged_dir: pathlib.Path) -> list[str]:
    return sorted(p.parent.name for p in packaged_dir.glob("*/SKILL.md"))


def render(packaged_dir: pathlib.Path, user_dir: pathlib.Path, name: str, harness: str) -> Rendered:
    packaged = packaged_dir / name / "SKILL.md"
    if not packaged.is_file():
        raise Problem(
            f"no packaged skill {name!r}; packaged: {', '.join(packaged_names(packaged_dir))}"
        )

    overlay, replacement = user_dir / name / "overlay.md", user_dir / name / "SKILL.md"
    if overlay.exists() and replacement.exists():
        raise Problem(f"{overlay.parent} has both overlay.md and SKILL.md; keep one")

    if replacement.exists():
        return Rendered(
            name,
            for_harness(replacement.read_text(), harness),
            f"{replacement} (replaces packaged)",
        )

    if not overlay.exists():
        return Rendered(name, for_harness(packaged.read_text(), harness), "packaged")

    added = overlay.read_text()
    if added.startswith("---\n"):
        raise Problem(
            f"{overlay} starts with frontmatter; an overlay only adds sections, so replace "
            "the whole skill with SKILL.md to change the frontmatter"
        )

    return Rendered(
        name,
        for_harness(f"{packaged.read_text().rstrip()}\n\n{added.strip()}\n", harness),
        f"packaged + {overlay}",
    )
