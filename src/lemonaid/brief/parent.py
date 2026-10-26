"""The `Parent:` header line: the Lemon-ID of the lemon that started this one."""

from . import frontmatter, frontmatter_edit


def with_parent(text: str, parent_id: str) -> str:
    """*text* with its `Parent:` line naming *parent_id*, or removed for "".

    Finds the line where `frontmatter` reads it (the header, or `## Now`, outside code
    fences). A line that already names *parent_id* is kept as written, with its session
    and date.
    """
    lines = text.splitlines()
    found = [(i, v) for i, key, v in frontmatter.header_lines(lines) if key == "parent"]
    keep = found[0][0] if found and frontmatter_edit.parent_id(found[0][1]) == parent_id else -1
    gone = {i for i, _ in found} - {keep}
    if not gone and (keep >= 0 or not parent_id):
        return text

    kept: list[str] = []
    for i, line in enumerate(lines):
        if i in gone:
            continue

        if i - 1 in gone and not line.strip() and (not kept or not kept[-1].strip()):
            continue

        kept.append(line)

    if keep >= 0 or not parent_id:
        return "\n".join(kept).rstrip("\n") + "\n"

    at = 1 if kept and kept[0].startswith("# ") else 0
    return (
        "\n".join([*kept[:at], "", f"Parent: {parent_id}", *kept[at:]]).lstrip("\n").rstrip("\n")
        + "\n"
    )
