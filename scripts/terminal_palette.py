#!/usr/bin/env python3
"""A terminal's colors, for `demo-screenshot.py` to draw a screen the way that terminal would.

    python3 scripts/terminal_palette.py > scripts/demo-palette.json

Run as a script, it prints the palette of iTerm2's default profile (or
`--profile NAME`), taking the Dark or Light variant from the system appearance
when the profile keeps separate ones.

A palette is JSON: `foreground`, `background`, `bold` (the color bold default
text is drawn in, or null for `foreground`), `ansi` (the 16 ANSI colors, black
through bright white), `bright_bold` (bold text in one of the first 8 ANSI
colors is drawn in its bright variant), and `minimum_contrast` (0 to 1).
"""

import argparse
import json
import plistlib
import subprocess
import sys
import typing as ty
from pathlib import Path

_ITERM_PREFERENCES = Path.home() / "Library/Preferences/com.googlecode.iterm2.plist"

# pyte's names for the 16 ANSI colors, in index order.
ANSI_NAMES = [
    *["black", "red", "green", "brown", "blue", "magenta", "cyan", "white"],
    *[f"bright{n}" for n in ["black", "red", "green", "brown", "blue", "magenta", "cyan", "white"]],
]


class Palette(ty.NamedTuple):
    foreground: str
    background: str
    bold: str | None
    ansi: list[str]
    bright_bold: bool
    minimum_contrast: float


def _rgb(colour: str) -> tuple[float, float, float]:
    value = colour.removeprefix("#")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return r, g, b


def _hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02x}" for c in (r, g, b))


def _brightness(r: float, g: float, b: float) -> float:
    return 0.30 * r + 0.59 * g + 0.11 * b


def blend(foreground: str, background: str, opacity: float) -> str:
    """`foreground` drawn at `opacity` over `background`."""
    return _hex(
        *(
            opacity * f + (1 - opacity) * b
            for f, b in zip(_rgb(foreground), _rgb(background), strict=False)
        )
    )


def with_contrast(foreground: str, background: str, minimum: float) -> str:
    """`foreground`, moved toward white or black until its brightness is `minimum` from `background`'s.

    iTerm2's "Minimum contrast" setting, as its color map computes it.
    """
    fg, bg = _rgb(foreground), _rgb(background)
    fg_brightness, bg_brightness = _brightness(*fg), _brightness(*bg)
    if abs(fg_brightness - bg_brightness) >= minimum:
        return foreground

    if fg_brightness < bg_brightness:
        target = bg_brightness - minimum
        if target < 0 and min(bg_brightness + minimum, 1) - bg_brightness > bg_brightness:
            target = bg_brightness + minimum
    else:
        target = bg_brightness + minimum
        if target > 1 and bg_brightness - max(bg_brightness - minimum, 0) > 1 - bg_brightness:
            target = bg_brightness - minimum
    target = min(max(target, 0.0), 1.0)
    towards = 1.0 if target > fg_brightness else 0.0
    p = (target - fg_brightness) / (towards - fg_brightness)
    return _hex(*(c + p * (towards - c) for c in fg))


def load(path: Path) -> Palette:
    palette = Palette(**json.loads(path.read_text()))
    if len(palette.ansi) != 16:
        raise SystemExit(f"{path}: `ansi` needs 16 colors, not {len(palette.ansi)}")

    return palette


def _iterm_profile(name: str) -> dict:
    with _ITERM_PREFERENCES.open("rb") as f:
        preferences = plistlib.load(f)
    profiles = preferences["New Bookmarks"]
    wanted = [
        p
        for p in profiles
        if (p["Name"] == name if name else p["Guid"] == preferences["Default Bookmark Guid"])
    ]
    if not wanted:
        raise SystemExit(f"no iTerm2 profile named {name!r}")

    return wanted[0]


def _dark_mode() -> bool:
    result = subprocess.run(
        ["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True
    )
    return result.stdout.strip() == "Dark"


def from_iterm(profile: dict, dark: bool) -> Palette:
    """The palette of an iTerm2 profile, as read from its preferences plist."""
    suffix = (
        (" (Dark)" if dark else " (Light)")
        if profile.get("Use Separate Colors for Light and Dark Mode")
        else ""
    )

    def setting(key: str, default: object = None) -> ty.Any:
        return profile.get(key + suffix, profile.get(key, default))

    def colour(key: str) -> str:
        c = setting(key)
        return _hex(*(float(c[f"{n} Component"]) for n in ("Red", "Green", "Blue")))

    # "Use Bright Bold" is iTerm2's old name for its "use a custom color for
    # bold text" setting; "Brighten Bold Text" is the bright-variant one.
    return Palette(
        foreground=colour("Foreground Color"),
        background=colour("Background Color"),
        bold=colour("Bold Color") if setting("Use Bright Bold", False) else None,
        ansi=[colour(f"Ansi {i} Color") for i in range(16)],
        bright_bold=bool(setting("Brighten Bold Text", True)),
        minimum_contrast=round(float(setting("Minimum Contrast", 0.0)), 3),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", default="", help="iTerm2 profile name (default: the default profile)"
    )
    appearance = parser.add_mutually_exclusive_group()
    appearance.add_argument("--dark", action="store_true", default=None)
    appearance.add_argument("--light", dest="dark", action="store_false")
    args = parser.parse_args()

    palette = from_iterm(
        _iterm_profile(args.profile), _dark_mode() if args.dark is None else args.dark
    )
    json.dump(palette._asdict(), sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
