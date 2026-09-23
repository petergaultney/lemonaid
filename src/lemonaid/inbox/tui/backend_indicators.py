"""Provider-colored model labels for inbox rows."""

import re

from rich.text import Text

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
_MODEL_FAMILIES = {
    "fable": ("Fable", "anthropic"),
    "opus": ("Opus", "anthropic"),
    "sonnet": ("Sonnet", "anthropic"),
    "haiku": ("Haiku", "anthropic"),
    "astra": ("Astra", "openai"),
    "sol": ("Sol", "openai"),
    "terra": ("Terra", "openai"),
    "luna": ("Luna", "openai"),
}


def backend_label(channel: str, overrides: dict[str, str]) -> str:
    prefix = channel.split(":")[0] if ":" in channel else channel
    return overrides.get(prefix, _DEFAULT_BACKEND_LABELS.get(prefix, prefix))


def _numeric_version(tokens: list[str]) -> str:
    """Read one dotted token or two short numeric tokens as a version."""
    if not tokens:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)+", tokens[0]):
        return tokens[0]

    parts = []
    for token in tokens[:2]:
        if not token.isdigit() or len(token) > 2:
            break
        parts.append(token)
    return ".".join(parts)


def _preceding_version(tokens: list[str]) -> str:
    """Read the numeric run immediately before a model family."""
    parts = []
    for token in reversed(tokens):
        if re.fullmatch(r"\d+(?:\.\d+)+", token):
            parts.insert(0, token)
            break
        if not token.isdigit() or len(token) > 2 or len(parts) == 2:
            break
        parts.insert(0, token)
    return _numeric_version(parts)


def _model_label(model: object) -> tuple[str, str] | None:
    if not isinstance(model, str):
        return None

    tokens = model.lower().replace("_", "-").replace("/", "-").split("-")
    for index, token in enumerate(tokens):
        family = _MODEL_FAMILIES.get(token)
        if not family:
            continue

        name, provider = family
        # Anthropic puts the version after the family (`opus-5-5`); OpenAI
        # currently puts it before (`5.6-sol`). Accept either so the display is
        # about the model rather than either provider's spelling convention.
        version = _numeric_version(tokens[index + 1 :]) or _preceding_version(tokens[:index])
        return (f"{name} {version}" if version else name, provider)

    return None


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
    indicator = _model_label(model)
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
