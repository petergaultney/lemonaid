"""Documents a lemon writes for someone to read, listed under `### Docs`."""

import dataclasses
import enum
import re
import urllib.parse
from collections import abc
from pathlib import Path

from .. import obsidian
from . import now_edit, output_doc, sections

_LINK = re.compile(r"\[(?P<label>(?:\\.|[^\]])*)\]\(<?(?P<url>[^>]+?)>?\)")


class Watch(enum.StrEnum):
    RELAY_COMMENTS = "Relay comments"
    ALL_EDITS = "All edits"


@dataclasses.dataclass(frozen=True)
class Row:
    path: Path
    purpose: str
    watch: Watch = Watch.RELAY_COMMENTS


def path_of(cell: str, vaults: abc.Iterable[Path] = ()) -> Path | None:
    match = _LINK.search(cell)
    value = match["url"] if match else cell.strip().strip("`")
    if value.startswith("obsidian://"):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(value).query)
        label = re.sub(r"\\([\\\[\]])", r"\1", match["label"]) if match else ""
        if label.startswith(("/", "~/")):
            return Path(label).expanduser().resolve()
        root = next((p for p in vaults if p.name == query.get("vault", [""])[0]), None)
        name = query.get("file", [""])[0]
        return root / (name if name.endswith(".md") else name + ".md") if root and name else None

    if value.startswith("file://"):
        parsed = urllib.parse.urlparse(value)
        if parsed.netloc not in {"", "localhost"}:
            return None
        return Path(urllib.parse.unquote(parsed.path)).resolve()

    if "://" in value or not value:
        return None

    return Path(urllib.parse.unquote(value)).expanduser().resolve()


def parse(body: abc.Sequence[str]) -> tuple[list[Row], list[str]]:
    lines = [line.strip() for line in body if line.strip()]
    if not lines:
        return [], []

    problems = []
    header = [c.strip().lower() for c in lines[0].strip("|").split("|")]
    if header != ["document", "purpose", "watch"]:
        return [], ["### Docs: use `| Document | Purpose | Watch |`"]
    if len(lines) < 2 or not all(
        re.fullmatch(r":?-+:?", c.strip()) for c in lines[1].strip("|").split("|")
    ):
        problems.append("### Docs: the header needs a separator line")
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip("|"))]
        path = path_of(cells[0]) if cells else None
        if not path or len(cells) != 3:
            problems.append(f"### Docs: invalid document row: {line}")
            continue

        try:
            watch = Watch(cells[2])
        except ValueError:
            problems.append("### Docs: Watch is Relay comments or All edits")
            continue
        if any(row.path == path for row in rows):
            problems.append(f"### Docs: {path} has two rows")
        rows.append(Row(path, cells[1], watch))
    return rows, problems


def rows(text: str) -> list[Row]:
    output = output_doc.read(text)
    listed = [
        row
        for section in sections.behavior(text)
        if section.heading.lower() == "docs"
        for row in parse(section.body)[0]
    ]
    return [
        *(
            [Row(output.resolve(), "Output document")]
            if output and all(r.path != output.resolve() for r in listed)
            else []
        ),
        *listed,
    ]


def cell(path: Path, vaults: abc.Collection[Path] = ()) -> str:
    path = path.expanduser().resolve()
    url = obsidian.vault_link(path, vaults) or path.as_uri()
    label = re.sub(r"([\\\[\]])", r"\\\1", str(path))
    return f"[{label}](<{url}>)"


def render(rows: abc.Iterable[Row], vaults: abc.Collection[Path] = ()) -> list[str]:
    lines = []
    for row in rows:
        document = cell(row.path, vaults)
        purpose = row.purpose.replace("|", r"\|")
        lines.append(f"| {document} | {purpose} | {row.watch.value} |")
    return ["| Document | Purpose | Watch |", "|---|---|---|", *lines] if lines else []


def _editable_rows(text: str) -> list[Row]:
    problems = [
        problem
        for section in sections.behavior(text)
        if section.heading.lower() == "docs"
        for problem in parse(section.body)[1]
    ]
    if problems:
        raise ValueError("Cannot rewrite ### Docs: " + "; ".join(problems))
    return rows(text)


def add(
    text: str,
    path: Path,
    purpose: str,
    watch: Watch = Watch.RELAY_COMMENTS,
    vaults: abc.Collection[Path] = (),
) -> str:
    path = path.expanduser().resolve()
    listed = _editable_rows(text)
    at = next((i for i, row in enumerate(listed) if row.path == path), len(listed))
    listed[at : at + 1] = [Row(path, purpose, watch)]
    return now_edit.with_section(text, "Docs", lambda body: render(listed, vaults))


def remove(text: str, path: Path, vaults: abc.Collection[Path] = ()) -> str:
    path = path.expanduser().resolve()
    listed = _editable_rows(text)
    if not any(row.path == path for row in listed):
        raise ValueError(f"No row in ### Docs for {path}")

    # Removing the output row also removes its legacy subscription.
    text = (
        re.sub(r"^Output-Doc:.*\n", "", text, flags=re.M)
        if bool((output := output_doc.read(text)) and output.resolve() == path)
        else text
    )
    return now_edit.with_section(
        text, "Docs", lambda body: render((row for row in listed if row.path != path), vaults)
    )
