"""Status text colors shared by the inbox and terminal confirmations."""

from .. import config, status_registry

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

# The inbox's own states for a brief with no status; statuses come from the registry.
_STATE_STYLES = {
    "active": "bold",
    "idle": "bright_black",
    "deaf": "bold #ff5c5c",
    "dead": "bold #ff5c5c",
}
_STATE_STYLES_LIGHT = {
    **_STATE_STYLES,
    "deaf": f"bold {ALERT_COLOR}",
    "dead": f"bold {ALERT_COLOR}",
}


def status_text_style(state: str, default: str = "", *, light: bool = False) -> str:
    """The foreground colour for a status word on the card's plain background."""
    if found := status_registry.by_name(config.brief_statuses()).get(state):
        return f"bold {found.text_light if light else found.text}"

    styles = _STATE_STYLES_LIGHT if light else _STATE_STYLES
    return styles.get(state, default)
