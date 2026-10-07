"""The line under a card's name: when, or how long, then which project and branch."""

import dataclasses
from collections import abc

from rich.text import Text

from ...brief import project
from ...config import PlacesConfig
from ...lemon_watchers import fish_path
from .utils import FIELD_STYLES, styled_cell, styled_project_cell

_SEPARATOR = " · "
# What gives way first when the line is too narrow. The project's name never
# does: it is the one field nothing else on the card says.
_CUT_ORDER = ("branch", "cwd", "project")
_MIN_CUT = 4  # three characters and the ellipsis; anything shorter is dropped


@dataclasses.dataclass(frozen=True)
class Part:
    field: str
    text: Text
    keep: int = 0  # cells a cut may not go below; 0 lets the part drop out
    project_name: str = ""


def project_part(places: PlacesConfig, cwd: str, branch: str, area: str = "") -> Part:
    """The project as an inbox row knows it, from its cwd and its brief's *area*.

    Outside every root with no branch either, nothing names a project, so the
    part is the cwd itself, as the row showed before it had a project.
    """
    if not cwd:
        return Part("project", Text(area), 0)
    if not branch and places.root_for(cwd) is None:
        return Part("cwd", Text(fish_path(cwd)), 0)

    name = project.label(places.roots, "", cwd)
    return Part("project", Text(f"{name}: {area}" if area else name), len(name), name)


def parts(
    fields: abc.Iterable[str],
    time: Text,
    where: Part,
    branch: str,
    cwd: str,
    is_unread: bool,
    age: str | Text = "",
    project_name_colors: bool = False,
    neutral_timing: bool = False,
) -> list[Part]:
    """The parts *fields* name, coloured like the row's cells; empty ones are left out.

    *where* is the row's `project_part`. When it fell back to the cwd, it keeps
    the project's place, and a `cwd` field in *fields* is left out. The `age`
    field is the brief's *age*, or the time on a card without a brief.
    """

    def part(field: str) -> Part | None:
        if field == "age" and age:
            if isinstance(age, Text):
                text = styled_cell(age.plain, is_unread, "time", neutral_timing=neutral_timing)
                for span in age.spans:
                    text.stylize(span.style, span.start, span.end)
            else:
                text = styled_cell(age, is_unread, "time", neutral_timing=neutral_timing)
            return Part("age", text, text.cell_len)
        if field in {"time", "age"}:
            return Part("time", time, time.cell_len)
        if field == "branch":
            return Part("branch", styled_cell(branch, is_unread, "branch"))
        if field == "cwd":
            return (
                None if falls_back else Part("cwd", styled_cell(fish_path(cwd), is_unread, "cwd"))
            )

        if field == "project" and project_name_colors and where.project_name:
            text = styled_project_cell(where.text.plain, where.project_name, is_unread)
        else:
            text = styled_cell(where.text.plain, is_unread, where.field)
        return dataclasses.replace(where, text=text)

    fields = tuple(fields)
    falls_back = where.field == "cwd" and "project" in fields
    return [p for f in fields if (p := part(f)) is not None and p.text.plain]


def _joined(line: abc.Sequence[Part]) -> Text:
    return Text(_SEPARATOR, style=FIELD_STYLES["backend"]).join(
        p.text for p in line if p.text.plain
    )


def _cut(part: Part, room: int) -> Part:
    """*part* in *room* cells: ellipsised, back to what it keeps, or dropped."""
    if room >= max(part.keep + 1, _MIN_CUT):
        text = part.text.copy()
        text.truncate(room, overflow="ellipsis")
        return dataclasses.replace(part, text=text)
    if part.keep:
        return dataclasses.replace(part, text=part.text[: part.keep])

    return dataclasses.replace(part, text=Text(""))


def fitted(line: abc.Sequence[Part], width: int) -> Text:
    """*line* joined into *width* cells, cutting the branch, then the cwd, then the area.

    Then the time goes, whole, so a project name that fits on its own is kept. A
    brief's age stays, since the card has no other line showing it: when the line
    still doesn't fit, it moves to the front, so the caller's truncation cuts the
    project rather than the age.
    """
    line = list(line)
    for field in _CUT_ORDER:
        for i, part in enumerate(line):
            over = _joined(line).cell_len - width
            if over <= 0:
                return _joined(line)
            if part.field == field:
                line[i] = _cut(part, part.text.cell_len - over)

    if _joined(line).cell_len > width:
        line = [part for part in line if part.field != "time"]
    if _joined(line).cell_len > width:
        line = sorted(line, key=lambda part: part.field != "age")

    return _joined(line)
