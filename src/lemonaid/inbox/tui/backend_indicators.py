"""Compact provider-colored model indicators for inbox rows."""

from rich.text import Text

from .utils import styled_cell

_DEFAULT_BACKEND_LABELS = {
    "claude": "A",
    "codex": "O",
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
_MODEL_INDICATORS = {
    "fable": ("F", "anthropic"),
    "opus": ("O", "anthropic"),
    "sonnet": ("S", "anthropic"),
    "haiku": ("H", "anthropic"),
    "astra": ("A", "openai"),
    "sol": ("S", "openai"),
    "terra": ("T", "openai"),
    "luna": ("L", "openai"),
}


def backend_label(channel: str, overrides: dict[str, str]) -> str:
    prefix = channel.split(":")[0] if ":" in channel else channel
    return overrides.get(prefix, _DEFAULT_BACKEND_LABELS.get(prefix, prefix))


def _model_indicator(model: object) -> tuple[str, str] | None:
    if not isinstance(model, str):
        return None

    tokens = model.lower().replace("_", "-").replace("/", "-").split("-")
    return next((_MODEL_INDICATORS[token] for token in tokens if token in _MODEL_INDICATORS), None)


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
    indicator = _model_indicator(model)
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
    return label
