"""Re-render installed skills when the packaged ones change, so an upgrade reaches every lemon.

The inbox TUI runs this once at startup. The stamp is each packaged SKILL.md's mtime and
size: a reinstall or a `git pull` in an editable checkout rewrites those files, which is
enough without knowing lemonaid's version. Only skills already installed are rewritten;
linking a harness entry stays `lemonaid skills install`'s job. Overlay edits are not
watched, and take effect on the next `skills install`.
"""

import os
import pathlib
import typing as ty

from .. import log
from . import compose, install

_logger = log.get_logger("skills.refresh")

_STAMP = ".packaged-stamp"


class Refreshed(ty.NamedTuple):
    rewritten: list[str]
    failed: list[str]  # skill names, or "skills" when the check itself failed


def _stamp(packaged_dir: pathlib.Path) -> str:
    return "".join(
        f"{e.name} {s.st_mtime_ns} {s.st_size}\n"
        for e in sorted(os.scandir(packaged_dir), key=lambda e: e.name)
        if e.is_dir()
        for s in [os.stat(os.path.join(e.path, "SKILL.md"))]
    )


def _rerender(
    packaged_dir: pathlib.Path, user_dir: pathlib.Path, rendered_dir: pathlib.Path
) -> Refreshed:
    rewritten, failed = [], []
    for name in compose.packaged_names(packaged_dir):
        if not install.is_rendered(rendered_dir, name):
            continue

        try:
            r = compose.render(packaged_dir, user_dir, name)
            if (rendered_dir / name / "SKILL.md").read_text() != r.text:
                install.write_rendered(rendered_dir, name, r.text)
                _logger.info("refreshed %s from %s", name, r.source)
                rewritten.append(name)
        except (OSError, UnicodeError, compose.Problem, install.Unmanaged) as e:
            _logger.warning("could not refresh skill %s: %s", name, e)
            failed.append(name)
    return Refreshed(rewritten, failed)


def refresh_if_stale(
    packaged_dir: pathlib.Path, user_dir: pathlib.Path, rendered_dir: pathlib.Path
) -> Refreshed:
    """Never raises for a file it can't read or write. The stamp is kept only when every
    skill refreshed, so a failure is reported again at the next check."""
    try:
        stamp = _stamp(packaged_dir)
        stamp_path = rendered_dir / _STAMP
        try:
            if stamp_path.read_text() == stamp:
                return Refreshed([], [])

        except (FileNotFoundError, UnicodeError):
            pass  # no stamp, or a damaged one: stale either way, and rewritten below

        result = _rerender(packaged_dir, user_dir, rendered_dir)
        if not result.failed:
            rendered_dir.mkdir(parents=True, exist_ok=True)
            tmp = rendered_dir / f".{_STAMP}.{os.getpid()}"
            tmp.write_text(stamp)
            tmp.replace(stamp_path)
        return result
    except OSError as e:
        _logger.warning("skills refresh failed: %s", e)
        return Refreshed([], ["skills"])


def refresh_installed() -> Refreshed:
    return refresh_if_stale(
        compose.PACKAGED_DIR, compose.default_user_dir(), install.default_rendered_dir()
    )


def notice(result: Refreshed) -> str:
    """One line for the user, or "" when there is nothing to say."""
    if result.failed:
        return (
            f"Could not refresh {', '.join(result.failed)} after a lemonaid upgrade (details in "
            f"{log.LOG_PATH}); run `lemonaid skills install`"
        )

    if result.rewritten:
        return f"Refreshed installed skills after a lemonaid upgrade: {', '.join(result.rewritten)}"

    return ""
