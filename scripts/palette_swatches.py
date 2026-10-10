"""Print the status colours and the generated name palette: `python scripts/palette_swatches.py`."""

import argparse
import colorsys
import sqlite3

from lemonaid import palette

MEANING = {
    "alert": "#c62828",
    "alert text": "#ff5c5c",
    "blocked": "#e3cf65",
    "merge": "#4fb35a",
    "approve": "#7e57c2",
    "review": "#8a5a2b",
    "running": "#00838f",
    "done": "#285995",
    "link": "#6cb6ff",
    "anthropic": "#d88760",
    "row cursor": "#17365d",
}


def hue_of(hex_: str) -> int:
    r, g, b = (int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))

    return round(colorsys.rgb_to_hls(r, g, b)[0] * 360)


def hls(h: float, light: float, sat: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h / 360, light, sat)

    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def block(hex_: str, label: str = "") -> str:
    r, g, b = (int(hex_[i : i + 2], 16) for i in (1, 3, 5))

    return f"\033[48;2;{r};{g};{b}m\033[38;2;0;0;0m {label:^9}\033[0m"


def main() -> None:
    print("UI meaning colours (hue in degrees):")
    for name, c in sorted(MEANING.items(), key=lambda kv: hue_of(kv[1])):
        print(f"  {block(c, name)} {c} hue {hue_of(c):3d}")

    print("\nHue wheel at L=0.62 S=0.75 (every 10 degrees); * = within 12 degrees of a meaning hue")
    meaning_hues = [hue_of(c) for c in MEANING.values()]
    for h in range(0, 360, 10):
        near = any(min(abs(h - m), 360 - abs(h - m)) <= 12 for m in meaning_hues)
        print(f"  {block(hls(h, .62, .75), str(h))} {'*' if near else ''}")


def contrast_with_black(hex_: str) -> float:
    r, g, b = (int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))

    return (palette._luminance(r, g, b) + 0.05) / 0.05


def slots() -> None:
    ratios = [contrast_with_black(c) for c in palette.SLOTS]
    print(f"\nContrast of black text on a slot: min {min(ratios):.1f}, max {max(ratios):.1f}")

    print(f"\nPalette slots ({len(palette.SLOTS)}), at least {palette.MIN_DISTANCE} apart:")
    for start in range(0, len(palette.SLOTS), 14):
        print(_strip(palette.SLOTS[start : start + 14]))


def _strip(colours: list[str]) -> str:
    return "  " + "".join(block(c, "")[:-4] + "  \033[0m" for c in colours)


def groups(db_path: str) -> None:
    """Check that no two groups' colours are close: for the groups in the DB at *db_path*, else sample names."""
    if db_path:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        names = [r[0] for r in conn.execute("SELECT name FROM lemon_groups ORDER BY position")]
        title = f"{len(names)} groups in {db_path}"
    else:
        names = (
            "oria mops relay watchers lemonaid protostellar eval infra docs ml tars lint".split()
        )
        title = f"{len(names)} sample group names"
    given = palette.assign_groups(names, {})
    print(f"\n{title}:")
    for name in sorted(names):
        print(f"{_strip([given[name]])} {name:<14} {given[name]}")
    if len(names) > 1:
        colours = list(given.values())
        gap, a, b = min(
            (palette.distance(a, b), a, b) for i, a in enumerate(colours) for b in colours[:i]
        )
        verdict = "ok" if gap >= palette.GROUP_MIN_DISTANCE else "TOO CLOSE"
        print(f"  closest pair {a} {b}: {gap:.3f} (minimum {palette.GROUP_MIN_DISTANCE}) {verdict}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default="", help="Check the groups in this inbox DB (opened read-only)"
    )
    args = parser.parse_args()
    main()
    slots()
    groups(args.db)
