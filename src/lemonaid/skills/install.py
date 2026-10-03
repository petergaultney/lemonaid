"""Write rendered skills to lemonaid's state directory, and link each harness's skill entry to them.

Claude and Codex both read `<skills dir>/<name>/SKILL.md`. Every harness links to the one
rendered copy, so they always get the same text. An entry is lemonaid's when it is a
symlink that resolves to that copy, directly or through another link (Codex's skill links
often point into Claude's). Anything else there is someone else's and is left alone.
"""

import enum
import os
import pathlib
import typing as ty

from ..tmux import navigation


class Outcome(enum.Enum):
    LINKED = "linked"
    CURRENT = "already linked"
    REFUSED = "refused"


class Result(ty.NamedTuple):
    harness: str
    entry: pathlib.Path
    outcome: Outcome
    detail: str


def _home_skills(override_var: str, home_var: str, default_home: str) -> pathlib.Path:
    override = os.environ.get(override_var)
    if override:
        return pathlib.Path(override).expanduser()

    return pathlib.Path(os.environ.get(home_var) or pathlib.Path.home() / default_home) / "skills"


def harness_skill_dirs() -> dict[str, pathlib.Path]:
    """Each harness's skills directory. The `LEMONAID_*_SKILLS_DIR` variables move them for tests and the sandbox."""
    return {
        "claude": _home_skills("LEMONAID_CLAUDE_SKILLS_DIR", "CLAUDE_CONFIG_DIR", ".claude"),
        "codex": _home_skills("LEMONAID_CODEX_SKILLS_DIR", "CODEX_HOME", ".codex"),
    }


def default_rendered_dir() -> pathlib.Path:
    return navigation.get_state_path() / "skills"


class Unmanaged(Exception):
    pass


_MARKER = ".lemonaid-skill"  # in each rendered directory, so a rerun knows it may rewrite it


def is_rendered(rendered_dir: pathlib.Path, name: str) -> bool:
    return (rendered_dir / name / _MARKER).is_file()


def write_rendered(rendered_dir: pathlib.Path, name: str, text: str) -> pathlib.Path:
    """The skill's rendered directory, holding `text` as its SKILL.md.

    Raises `Unmanaged` if something lemonaid didn't create is already there.
    """
    skill_dir = rendered_dir / name
    if skill_dir.is_symlink() or (skill_dir.exists() and not (skill_dir / _MARKER).is_file()):
        raise Unmanaged(f"{skill_dir} exists and lemonaid didn't create it")

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / _MARKER).touch()
    tmp = skill_dir / f".SKILL.md.{os.getpid()}"  # two lma instances may refresh at once
    tmp.write_text(text)
    tmp.replace(skill_dir / "SKILL.md")
    return skill_dir


def _verified(entry: pathlib.Path, text: str) -> bool:
    try:
        return (entry / "SKILL.md").read_text() == text
    except OSError:
        return False


def link(harness: str, entry: pathlib.Path, skill_dir: pathlib.Path, text: str) -> Result:
    """Point `entry` at `skill_dir`, unless something lemonaid didn't create is already there."""
    if entry.is_symlink() and entry.resolve() == skill_dir.resolve():
        return (
            Result(harness, entry, Outcome.CURRENT, "")
            if _verified(entry, text)
            else Result(harness, entry, Outcome.REFUSED, f"{entry}/SKILL.md does not match")
        )

    if entry.is_symlink():
        return Result(
            harness,
            entry,
            Outcome.REFUSED,
            f"{entry} links to {os.readlink(entry)}, which lemonaid didn't create",
        )

    if entry.exists():
        return Result(
            harness, entry, Outcome.REFUSED, f"{entry} exists and lemonaid didn't create it"
        )

    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.symlink_to(skill_dir)
    return (
        Result(harness, entry, Outcome.LINKED, "")
        if _verified(entry, text)
        else Result(harness, entry, Outcome.REFUSED, f"{entry}/SKILL.md does not match")
    )
