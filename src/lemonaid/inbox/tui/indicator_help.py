"""The inbox family indicators in the question-mark reference."""

from .rows import parent_markers


def sections() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        (
            "Family indicators",
            [
                (
                    f"{parent_markers.PARENT} (bright)",
                    "Parent of the row under the cursor, when shown",
                ),
                (
                    f"{parent_markers.CHILD} (bright)",
                    "Direct child of the row under the cursor, when shown",
                ),
                ("\u21933 (dim)", "Three active direct children, all shown"),
                ("\u21931/3 (dim)", "One shown out of three active direct children"),
                ("Scope", "Across groups and both inbox tables; each child counts once"),
                ("Visibility", "Only shown relatives get arrows; hidden rows stay hidden"),
                ("Totals", "Include hidden/folded; exclude archived/snoozed"),
                ("Highlight", "Arrows follow the cursor; a group header clears them"),
            ],
        )
    ]
