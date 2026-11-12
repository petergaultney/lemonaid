"""The text a lemon reads for one watch batch: its content, a rule, and what the lemon needs to know.

Built once here; a transport (`push_scout`, `codex_scout`, the rearm line) only sends it.
"""

from . import clip, delivery

_RULE = "\n\n---\n"  # so the closing sentences are not read as part of the content
_DEFAULT_LEAD = "lemonaid watch event:"


def _closing(message: str, next_one: str = "") -> str:
    many = delivery.events_in(message) > 1
    return " ".join(
        [
            *(["Handle all of it."] if many else []),
            *(
                [
                    "Comments are included in full"
                    + (
                        "; fetch one only if a cut marks it as omitted."
                        if clip.was_cut(message)
                        else "."
                    )
                ]
                if delivery.has_comments(message)
                else []
            ),
            *(
                [f"lemonaid keeps watching{f' and {next_one}' if many else ''}."]
                if next_one
                else []
            ),
        ]
    )


def compose(message: str, next_one: str = "", then: str = "") -> str:
    """*message* under its label, then a rule and the closing.

    *next_one* says where lemonaid delivers the next batch; it is "" when the lemon rearms
    a waiter instead, and *then* names that rearm.
    """
    closing = " ".join(filter(None, [_closing(message, next_one), then]))
    return f"{delivery.label_of(message) or _DEFAULT_LEAD}\n\n{message}{_RULE}{closing}"
