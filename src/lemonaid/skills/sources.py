"""Where each installable skill comes from: lemonaid's packaged skills, then each configured
source (see source_config.py), in order.

A source is a directory of `<name>/SKILL.md`, written as the packaged ones are. Its
optional `skills.toml` lists `optional = [...]`: skills that install only when named, so
installing a source doesn't start a workflow nobody asked for. Skill names are shared by
every harness, so a name an earlier source has is refused, not replaced.
"""

import dataclasses
import pathlib
import shutil
import subprocess
import sys
import tomllib
from collections import abc

from . import compose, install
from .source_config import Source

PACKAGED = "lemonaid"

Report = abc.Callable[[str], None]


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


@dataclasses.dataclass(frozen=True)
class Located:
    name: str
    dir: pathlib.Path
    optional: frozenset[str] = frozenset()


def fetched_dir(source: Source) -> pathlib.Path:
    return install.rendered_root().parent / "skill-sources" / source.name


def _run(
    source: Source, argv: abc.Sequence[str], directory: pathlib.Path, report: Report
) -> str | None:
    try:
        done = subprocess.run(
            [arg.replace("{dir}", str(directory)) for arg in argv],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        report(f"skill source {source.name}: {e}")
        return None

    if done.returncode != 0:
        report(f"skill source {source.name}: {done.stderr.strip()[-500:]}")
        return None

    return done.stdout


def _directory(source: Source, update: bool, report: Report) -> pathlib.Path | None:
    """The source's directory, fetched first when it is missing, or updated when asked."""
    if source.path:
        return pathlib.Path(source.path).expanduser()

    if source.command:
        printed = _run(source, source.command, pathlib.Path(), report)
        return pathlib.Path(printed.strip()).expanduser() if printed and printed.strip() else None

    directory = fetched_dir(source)
    if not directory.exists():
        # fetched beside it and moved in only on success, so a failed fetch is tried again
        fetching = directory.with_name(f".{directory.name}.fetching")
        shutil.rmtree(fetching, ignore_errors=True)
        fetching.parent.mkdir(parents=True, exist_ok=True)
        if _run(source, source.fetch, fetching, report) is None or not fetching.is_dir():
            shutil.rmtree(fetching, ignore_errors=True)
            return None

        fetching.rename(directory)

    elif update and source.update and _run(source, source.update, directory, report) is None:
        return None

    return directory


def _optional(directory: pathlib.Path, report: Report) -> frozenset[str]:
    try:
        manifest = tomllib.loads((directory / "skills.toml").read_text())
    except FileNotFoundError:
        return frozenset()

    except (OSError, tomllib.TOMLDecodeError) as e:
        report(f"{directory / 'skills.toml'}: {e}")
        return frozenset()

    names = manifest.get("optional", [])
    return (
        frozenset(n for n in names if isinstance(n, str))
        if isinstance(names, list)
        else frozenset()
    )


def locate(
    sources: abc.Iterable[Source], update: bool = False, report: Report = _stderr
) -> list[Located]:
    """lemonaid's packaged skills first, then every source whose directory could be found;
    a source that can't be found is reported on stderr and left out."""
    found = [Located(PACKAGED, compose.PACKAGED_DIR)]
    for source in sources:
        directory = _directory(source, update, report)
        if directory is None or not directory.is_dir():
            report(f"skill source {source.name}: no directory {directory or ''}")
            continue

        found.append(Located(source.name, directory, _optional(directory, report)))
    return found


def catalog(located: abc.Iterable[Located], report: Report = _stderr) -> dict[str, Located]:
    """Each skill name to the source that installs it: the first that has it."""
    owners: dict[str, Located] = {}
    for source in located:
        for name in compose.packaged_names(source.dir):
            if name in owners:
                report(
                    f"skill {name!r} in source {source.name} is ignored: "
                    f"{owners[name].name} already has it"
                )
            else:
                owners[name] = source
    return owners


def default_names(owners: abc.Mapping[str, Located]) -> list[str]:
    return sorted(name for name, source in owners.items() if name not in source.optional)
