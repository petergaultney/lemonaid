"""The brief view's own key reference."""

from ....config import KeybindingsConfig
from ..help_screen import HelpScreen


def rows(kb: KeybindingsConfig, browsing: bool) -> list[tuple[str, list[tuple[str, str]]]]:
    questions = [
        (getattr(kb, field), label)
        for field, label in (
            ("question_previous", "Previous Needs or saved-answer entry"),
            ("question_next", "Next Needs or saved-answer entry"),
            ("answer", "Answer the selected question"),
            ("answer_yes", 'Send "Yes, approved"'),
            ("more_detail", "Ask for more detail"),
        )
        if getattr(kb, field)
    ]
    answers = [
        (getattr(kb, field), label)
        for field, label in (
            ("answer_archive", "Archive the selected live saved answer"),
            ("answer_archive_all", "Archive all live answers in the selected brief"),
            ("answers_expand", "Expand or collapse archived answers"),
        )
        if getattr(kb, field)
    ]
    navigation = [
        ("Mouse wheel", "Scroll the brief"),
        ("PgUp / PgDn", "Scroll a page"),
        ("Home / End", "Scroll to the top or bottom"),
        ("?", "Show this help"),
        (
            " / ".join([*(kb.quit if browsing else "q"), "Esc"]),
            "Return to the inbox" if browsing else "Close the brief",
        ),
    ]
    if browsing:
        up, down = kb.up_down if len(kb.up_down) == 2 else ("", "")
        navigation.insert(0, (" / ".join(k for k in ("Up / Down", up, down) if k), "Browse briefs"))
        navigation.extend(
            [
                (" / ".join(["Enter", *kb.select]), "Switch to the shown session"),
                (
                    " / ".join([*kb.brief, *([kb.brief_key] if kb.brief_key else [])]),
                    "Toggle the brief view",
                ),
            ]
        )
    else:
        navigation.insert(0, ("Up / Down", "Scroll the brief"))
    session = [
        (" / ".join(getattr(kb, field)), label)
        for field, label in (
            ("mark_read", "Mark the shown session read"),
            ("mark_unread", "Mark the shown session unread"),
            ("rename", "Rename the shown session"),
            ("resume_detached", "Resume when its terminal is unavailable"),
            ("undo", "Undo the last inbox change"),
            ("refresh", "Refresh"),
            ("flip_position", "Move the inbox pane between top and left"),
        )
        if browsing and getattr(kb, field)
    ]
    navigation = [(key, label) for key, label in navigation if key]
    return [
        ("Moving around", navigation),
        ("Needs and selection", questions),
        ("Saved chat answers", answers),
        ("Shown session", session),
        (
            "Mouse",
            [
                ("Click", "Select an entry"),
                ("Need again", "Open its answer box"),
                ("Answer again", "Archive that live answer"),
                ("Archived again", "Collapse archived answers"),
                ("Click link", "Open the link"),
                ("Double-click", "Select a word"),
                ("Drag", "Select text"),
            ],
        ),
    ]


class BriefHelpScreen(HelpScreen):
    def __init__(
        self,
        keys: KeybindingsConfig,
        browsing: bool,
        selected_hint: str = "",
        *,
        wide: bool = False,
    ) -> None:
        super().__init__(
            keys, wide, title="Brief keys", sections=rows(keys, browsing), context=selected_hint
        )
