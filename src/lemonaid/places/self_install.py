"""Protection for places that contain the active editable lemonaid install."""

import sys
import tomllib
from pathlib import Path

from . import target


def editable_install_source() -> Path | None:
    """The checkout a uv-installed lemonaid command imports from, if editable."""
    receipt = Path(sys.prefix) / "uv-receipt.toml"
    try:
        data = tomllib.loads(receipt.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None

    requirements = data.get("tool", {}).get("requirements", [])
    for requirement in requirements:
        if requirement.get("name") == "lemonaid-inbox" and (
            editable := requirement.get("editable")
        ):
            return Path(editable).expanduser().resolve()

    return None


def editable_install_refusal(doomed: target.TossTarget) -> str:
    """Refuse to release the checkout backing this editable lemonaid install."""
    source = editable_install_source()
    if source is None:
        return ""

    for place in doomed.places:
        directory = place.directory.resolve()
        if source == directory or source.is_relative_to(directory):
            return (
                f"Cannot release {place.key!r}: the installed lemonaid is editable from "
                f"{source}. Reinstall lemonaid non-editably before releasing this place."
            )

    return ""
