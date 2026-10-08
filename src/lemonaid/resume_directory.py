"""A surviving directory for a conversation whose original directory is gone."""

from pathlib import Path


def surviving_directory(cwd: str) -> str:
    path = Path(cwd).expanduser().absolute()
    return str(next(candidate for candidate in (path, *path.parents) if candidate.is_dir()))


def codex_directory(cwd: str, argv: list[str]) -> tuple[str, list[str]]:
    for index, argument in enumerate(argv):
        if argument in {"--cd", "-C"} and index + 1 < len(argv):
            directory = surviving_directory(str(Path(cwd) / Path(argv[index + 1]).expanduser()))
            return directory, [*argv[: index + 1], directory, *argv[index + 2 :]]

        prefix = next(
            (
                prefix
                for prefix in ("--cd=", "-C=", "-C")
                if argument.startswith(prefix) and len(argument) > len(prefix)
            ),
            "",
        )
        if prefix:
            directory = surviving_directory(
                str(Path(cwd) / Path(argument[len(prefix) :]).expanduser())
            )
            return directory, [*argv[:index], f"{prefix}{directory}", *argv[index + 1 :]]

    return cwd, [*argv, "--cd", cwd]
