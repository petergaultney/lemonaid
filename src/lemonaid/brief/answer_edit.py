"""Archive live answers through the same checked edit in the CLI and TUI."""

from pathlib import Path

from . import answer_archive, answers, sections, store, verbs_cli


def archive(path: Path, count: int | None, entry: str = "") -> int:
    path = path.resolve()
    if error := store.outside_error(path):
        raise ValueError(error)

    moved: list[str] = []

    def change(before: str) -> str:
        if entry:
            heading = next(
                (h for h in sections.scan(before) if h.level == 2 and h.name.lower() == "answers"),
                None,
            )
            if heading is None:
                raise ValueError("That answer is missing; refresh and select it again")
            body = "\n".join(sections.body(before, heading))
            if entry not in body:
                raise ValueError("That answer has changed; refresh and select it again")
            # Match a whole entry, not text quoted inside a different answer.
            starts = [h.start for h in sections.scan(body) if h.level == 3]
            lines = body.splitlines()
            chunks = [
                "\n".join(lines[a:b]).strip()
                for a, b in zip(starts, [*starts[1:], len(lines)], strict=False)
            ]
            if chunks.count(entry) != 1:
                raise ValueError("That answer is missing or ambiguous; refresh and select it again")
            chunks.remove(entry)
            after = sections.replace(before, heading, [*lines[: starts[0]], "\n\n".join(chunks)])
            entries = [entry]
        else:
            after, entries = answers.take(before, count)
        verbs_cli.validate(path, before, after)
        if entries:
            answer_archive.save(path, entries)
        moved[:] = entries
        return after

    store.edit(path, change)
    return len(moved)
