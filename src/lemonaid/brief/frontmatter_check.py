"""What `brief check` reports about a brief's frontmatter block."""

from . import frontmatter


def problems(text: str) -> list[str]:
    """Everything wrong with *text*'s block; nothing for a brief without one."""
    if not frontmatter.has_block(text):
        return []

    try:
        found = frontmatter.fields(text)
    except ValueError as error:
        return [str(error)]

    created = found.get("created")
    by = created.get("by") if isinstance(created, dict) else None
    editors = frontmatter.contributors(found)
    parties = found.get("responsible-parties")
    return [
        *([] if found.get("type") == "Brief" else ["The frontmatter's `type` should be `Brief`"]),
        *(
            []
            if isinstance(created, dict) and created.get("at")
            else ["The frontmatter has no `created: { at: ... }`"]
        ),
        *(
            []
            if isinstance(parties, list) and parties
            else ["The frontmatter has no `responsible-parties` list"]
        ),
        *(
            []
            if not by or (editors and editors[0] == by)
            else [f"The frontmatter's `contributors` should start with its creator, {by}"]
        ),
        *(
            f"A `{label}:` header line sits beside the frontmatter; set it in the frontmatter"
            for label in frontmatter.stray_labels(text)
        ),
    ]
