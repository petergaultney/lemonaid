"""Short model labels shared by the inbox and brief display."""

import re

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


def _numeric_version(tokens: list[str]) -> str:
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
    parts = []
    for token in reversed(tokens):
        if re.fullmatch(r"\d+(?:\.\d+)+", token):
            parts.insert(0, token)
            break
        if not token.isdigit() or len(token) > 2 or len(parts) == 2:
            break
        parts.insert(0, token)
    return _numeric_version(parts)


def model_label(model: object) -> tuple[str, str] | None:
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
