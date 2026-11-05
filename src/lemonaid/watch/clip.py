"""Size limits for text pushed into a lemon, which points it back at the source when cut."""

COMMENT_LIMIT = 4000
BATCH_LIMIT = 30000


def shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    return (
        f"{text[:limit]}... ({len(text) - limit} characters omitted; read the source for the rest)"
    )


def share(parts: list[str], limit: int = BATCH_LIMIT) -> list[str]:
    """Each part cut to an equal share of *limit*, so every source stays identifiable."""
    return [shorten(part, limit // len(parts)) for part in parts]
