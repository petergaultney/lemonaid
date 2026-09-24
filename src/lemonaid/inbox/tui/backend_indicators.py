"""Provider-colored model labels for inbox rows."""

from rich.text import Text

from ..model_label import model_label
from .utils import styled_cell

_DEFAULT_BACKEND_LABELS = {
    "claude": "Anthropic",
    "codex": "OpenAI",
    "openclaw": "🦞",
}
_BACKEND_PROVIDERS = {
    "claude": "anthropic",
    "codex": "openai",
}
_PROVIDER_STYLES = {
    "anthropic": "#d88760",
    "openai": "#c0c4c8",
}


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
) -> Text:
    prefix = channel.split(":")[0] if ":" in channel else channel
    indicator = model_label(model)
    label = styled_cell(
        indicator[0] if indicator else backend_label(channel, overrides),
        is_unread,
        "backend",
        history=history,
    )
    provider = model_provider if isinstance(model_provider, str) else ""
    provider = provider or (indicator[1] if indicator else _BACKEND_PROVIDERS.get(prefix, ""))
    if style := _PROVIDER_STYLES.get(provider.lower()):
        label.stylize(style)
    label.justify = "right"
    return label
