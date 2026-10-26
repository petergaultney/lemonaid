"""A lemon's model label color, by its provider, wherever a model is shown."""

_BACKEND_PROVIDERS = {
    "claude": "anthropic",
    "codex": "openai",
}
_PROVIDER_COLORS = {
    "anthropic": "#d88760",
    "openai": "#c0c4c8",
}


def provider(channel: str, model_provider: str = "") -> str:
    """*model_provider* when known, else the provider of the channel's backend."""
    prefix = channel.split(":")[0] if ":" in channel else channel
    return model_provider or _BACKEND_PROVIDERS.get(prefix, "")


def color(channel: str, model_provider: str = "") -> str:
    """The provider's color, or "" for one without."""
    return _PROVIDER_COLORS.get(provider(channel, model_provider).lower(), "")
