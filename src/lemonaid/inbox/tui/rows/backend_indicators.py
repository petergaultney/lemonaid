"""Provider-colored model labels for inbox rows."""

from rich.text import Text

from ... import provider_color
from ...model_label import model_label
from ..utils import styled_cell
from . import context_reading

_DEFAULT_BACKEND_LABELS = {
    "claude": "Anthropic",
    "codex": "OpenAI",
    "openclaw": "🦞",
}


def provider_style(channel: str, model_provider: str = "") -> str:
    """The colour of a lemon's model label: its provider's, else its backend's provider's."""
    return provider_color.color(channel, model_provider)


def backend_label(channel: str, overrides: dict[str, str]) -> str:
    prefix = channel.split(":")[0] if ":" in channel else channel
    return overrides.get(prefix, _DEFAULT_BACKEND_LABELS.get(prefix, prefix))


def backend_text(
    channel: str,
    overrides: dict[str, str],
    is_unread: bool,
    *,
    model: object = "",
    model_provider: object = "",
    history: bool = False,
    context_percent: int | None = None,
) -> Text:
    indicator = model_label(model)
    label = styled_cell(
        indicator[0] if indicator else backend_label(channel, overrides),
        is_unread,
        "backend",
        history=history,
    )
    provider = model_provider if isinstance(model_provider, str) else ""
    if style := provider_color.color(channel, provider or (indicator[1] if indicator else "")):
        label.stylize(style)
    if context_percent is not None:
        label = context_reading.text(context_percent) + label
    label.justify = "right"
    return label
