"""Status text colors shared by the inbox and terminal confirmations."""

ATTENTION_COLOR = "#e3cf65"
ATTENTION_TEXT_LIGHT = "#8a6d00"

MERGE_COLOR = "#4fb35a"
ALERT_COLOR = "#c62828"
REVIEW_COLOR = "#8a5a2b"
APPROVE_COLOR = "#7e57c2"
RUNNING_COLOR = "#00838f"
# The running process named on a card, lighter than the headline fill so it reads on the plain background.
RUNNING_TEXT_COLOR = "#4fc3cc"
RUNNING_TEXT_COLOR_LIGHT = "#00707a"

_STATE_STYLES = {
    "alert": "bold #ff5c5c",
    "blocked": f"bold {ATTENTION_COLOR}",
    "merge": f"bold {MERGE_COLOR}",
    "approve": "bold #b39ddb",
    "review": "bold #c08a52",
    "running": f"bold {RUNNING_TEXT_COLOR}",
    "done": "bold #6f9fe0",
    "working": "bold",
    "waiting": "bright_black",
}
_STATE_STYLES_LIGHT = {
    **_STATE_STYLES,
    "alert": f"bold {ALERT_COLOR}",
    "blocked": f"bold {ATTENTION_TEXT_LIGHT}",
    "merge": "bold #2e7d32",
    "approve": "bold #5e35b1",
    "review": f"bold {REVIEW_COLOR}",
    "running": f"bold {RUNNING_TEXT_COLOR_LIGHT}",
    "done": "bold #285995",
}


def status_text_style(state: str, default: str = "", *, light: bool = False) -> str:
    """The foreground colour for a status word on the card's plain background."""
    styles = _STATE_STYLES_LIGHT if light else _STATE_STYLES
    return styles.get(state, default)
