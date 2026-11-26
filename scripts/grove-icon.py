"""Draw the lemon grove icon: a lemon slice whose membranes are a tree, with a straw behind it.

Every membrane is one filled shape: a bough that tapers from its fork and arrives at the
pulp's edge square on, then flares into the pith with curved fillets, so nothing ends in a cut.
`detail` frames the icon around the lemon, with room for the straw inside the circle a phone
crops an icon to. `tab` draws for a browser tab's 16 to 32 pixels: filling its square, with wider
membranes and a heavier rind, and without the texture.

    python scripts/grove-icon.py tab > src/lemonaid/grove/web/icon.svg
    python scripts/grove-icon.py detail > docs/images/lemon-grove-icon.svg
    rsvg-convert -w 180 -h 180 docs/images/lemon-grove-icon.svg -o src/lemonaid/grove/web/apple-touch-icon.png
    rsvg-convert -w 1024 -h 1024 docs/images/lemon-grove-icon.svg -o docs/images/lemon-grove-icon.png
"""

import math
import sys

CX, CY = 118.0, 138.0
RIND, PITH, PULP = 100.0, 90.0, 82.0


def _polar(angle_deg: float, r: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def _pt(p: tuple[float, float]) -> str:
    return f"{p[0]:.2f} {p[1]:.2f}"


def _quad(a, c, b, t):
    u = 1 - t
    return (
        u * u * a[0] + 2 * u * t * c[0] + t * t * b[0],
        u * u * a[1] + 2 * u * t * c[1] + t * t * b[1],
    )


def _tangent(a, c, b, t):
    u = 1 - t
    dx, dy = (
        2 * u * (c[0] - a[0]) + 2 * t * (b[0] - c[0]),
        2 * u * (c[1] - a[1]) + 2 * t * (b[1] - c[1]),
    )
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _bough(start, angle: float, reach: float, w0: float, w1: float, flare: float) -> str:
    """From *start* to the pulp's edge at *angle*, arriving square on: *w0* wide at the start,
    *w1* at the edge, then flaring by *flare* on each side into the pith."""
    tip = _polar(angle, PULP)
    ctrl = _polar(angle, PULP - reach)
    steps = 40
    side_a, side_b = [], []
    for i in range(steps + 1):
        t = i / steps
        x, y = _quad(start, ctrl, tip, t)
        tx, ty = _tangent(start, ctrl, tip, t)
        w = (w0 + (w1 - w0) * t) / 2
        side_a.append((x + ty * w, y - tx * w))
        side_b.append((x - ty * w, y + tx * w))
    k = steps - 9  # where the fillets leave the bough
    a = math.radians(angle)
    ccw_a = math.cos(a) * (side_a[k][1] - CY) - math.sin(a) * (side_a[k][0] - CX) < 0
    ccw, cw = (side_a, side_b) if ccw_a else (side_b, side_a)
    along = _tangent(start, ctrl, tip, k / steps)
    spread = math.degrees((w1 / 2 + flare) / PULP)

    def corner(side: list, sign: int) -> tuple[tuple[float, float], tuple[float, float]]:
        """Where a fillet leaving the bough along *side* lands on the rim, arriving along the
        rim, and the control point that curves it there."""
        land = _polar(angle + sign * spread, PULP)
        rim = math.radians(angle + sign * spread + 90)
        return _meet(side[k], along, land, (math.cos(rim), math.sin(rim))), land

    ccw_corner, ccw_land = corner(ccw, -1)
    cw_corner, cw_land = corner(cw, +1)
    return (
        f"M{_pt(start)} "
        + " ".join(f"L{_pt(p)}" for p in ccw[: k + 1])
        + f" Q{_pt(ccw_corner)} {_pt(ccw_land)}"
        + f" L{_pt(_polar(angle - spread, PULP + 6))} L{_pt(_polar(angle + spread, PULP + 6))}"
        + f" L{_pt(cw_land)} Q{_pt(cw_corner)} {_pt(cw[k])} "
        + " ".join(f"L{_pt(p)}" for p in reversed(cw[:k]))
        + " Z"
    )


def _meet(p, d, q, e) -> tuple[float, float]:
    """Where the line through p along d crosses the line through q along e."""
    det = d[0] * -e[1] - d[1] * -e[0]
    if abs(det) < 1e-9:
        return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    u = ((q[0] - p[0]) * -e[1] - (q[1] - p[1]) * -e[0]) / det
    return (p[0] + u * d[0], p[1] + u * d[1])


def _neighbours(angles: list[float]) -> list[tuple[float, float]]:
    """Each pair of directions next to each other around a fork."""
    ordered = sorted(a % 360 for a in angles)
    return list(zip(ordered, [*ordered[1:], ordered[0] + 360], strict=False))


def _web(at: tuple[float, float], a1: float, a2: float, k: float) -> str:
    """Fill the crotch between two branches leaving *at*, with a curved edge, so the segment
    between them has a rounded corner."""
    gap = a2 - a1
    reach = (26 if gap < 80 else 20 if gap < 130 else 14) * k
    p1 = (at[0] + reach * math.cos(math.radians(a1)), at[1] + reach * math.sin(math.radians(a1)))
    p2 = (at[0] + reach * math.cos(math.radians(a2)), at[1] + reach * math.sin(math.radians(a2)))
    return f"M{_pt(at)} L{_pt(p1)} Q{_pt(at)} {_pt(p2)} Z"


def _tree(detail: bool, colour: str) -> str:
    k = 1.0 if detail else 1.5
    hub = (CX, CY - 4)
    fl, fr = (CX - 25, CY - 28), (CX + 25, CY - 28)
    low = (CX, CY + 40)
    boughs = [
        _bough(hub, 90, 44, 9 * k, 11 * k, 12 * k),  # the trunk, rooted in the pith
        _bough(low, 152, 34, 9 * k, 5 * k, 7 * k),
        _bough(low, 28, 34, 9 * k, 5 * k, 7 * k),
        _bough(hub, -90, 40, 9 * k, 5 * k, 7 * k),
        _bough(fl, -163, 30, 7.5 * k, 4.5 * k, 7 * k),
        _bough(fl, -124, 30, 7.5 * k, 4.5 * k, 7 * k),
        _bough(fr, -56, 30, 7.5 * k, 4.5 * k, 7 * k),
        _bough(fr, -17, 30, 7.5 * k, 4.5 * k, 7 * k),
    ]
    limbs = [
        f"M{_pt(hub)} Q{_pt((CX - 13, CY - 10))} {_pt(fl)}",
        f"M{_pt(hub)} Q{_pt((CX + 13, CY - 10))} {_pt(fr)}",
    ]
    joints = [(hub, 7.5), (fl, 4.2), (fr, 4.2), (low, 5.4)]

    def toward(a, b):
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

    def ctrl(angle, reach):
        return _polar(angle, PULP - reach)

    forks = {
        hub: [90, -90, toward(hub, (CX - 13, CY - 10)), toward(hub, (CX + 13, CY - 10))],
        fl: [
            toward(fl, (CX - 13, CY - 10)),
            toward(fl, ctrl(-163, 30)),
            toward(fl, ctrl(-124, 30)),
        ],
        fr: [toward(fr, (CX + 13, CY - 10)), toward(fr, ctrl(-56, 30)), toward(fr, ctrl(-17, 30))],
        low: [-90, 90, toward(low, ctrl(152, 34)), toward(low, ctrl(28, 34))],
    }
    webs = [_web(at, a1, a2, k) for at, angles in forks.items() for a1, a2 in _neighbours(angles)]
    return (
        f'<g fill="{colour}">'
        + "".join(f'<path d="{d}"/>' for d in boughs + webs)
        + "".join(f'<circle cx="{p[0]:.2f}" cy="{p[1]:.2f}" r="{r * k:.2f}"/>' for p, r in joints)
        + "</g>"
        + f'<g stroke="{colour}" stroke-width="{8.4 * k:.1f}" stroke-linecap="round" fill="none">'
        + "".join(f'<path d="{d}"/>' for d in limbs)
        + "</g>"
    )


def _streaks() -> str:
    """Juice vesicles: short radial strokes through the pulp."""
    out = []
    for i in range(0, 360, 5):
        for r0, r1, shift in ((24, 46, 0), (52, 76, 2.5)):
            out.append(f"M{_pt(_polar(i + shift, r0))} L{_pt(_polar(i + shift, r1))}")
    return " ".join(out)


def _pores() -> str:
    out = []
    for i in range(0, 360, 8):
        for r, shift in ((93.8, 0), (97.2, 4)):
            x, y = _polar(i + shift, r)
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="0.85"/>')
    return "".join(out)


_STRAW = {"at": -60.0, "inset": 38.0, "turn": -62.0, "length": 78.0, "width": 22.0}


def _placed(p: tuple[float, float]) -> tuple[float, float]:
    """*p*, in the straw's own frame, where the straw stands behind the fruit."""
    base, a = _polar(_STRAW["at"], RIND - _STRAW["inset"]), math.radians(_STRAW["turn"])
    return base[0] + p[0] * math.cos(a) - p[1] * math.sin(a), base[1] + p[0] * math.sin(a) + p[
        1
    ] * math.cos(a)


def _framed(detail: bool, fill: float = 0.92) -> str:
    """The square viewBox: for *detail*, around the fruit, whose inscribed circle holds the fruit
    and the straw with *fill* of its radius used; otherwise the smallest square that holds them."""
    h, length = _STRAW["width"] / 2, _STRAW["length"]
    straw = [_placed((length * i / 20, y)) for i in range(21) for y in (-h, h)]
    if detail:
        fruit = RIND + 6  # the rind's stroke and its drop shadow
        half = max(fruit, *(math.hypot(x - CX, y - CY) + 1.5 for x, y in straw)) / fill
        return f"{CX - half:.2f} {CY - half:.2f} {2 * half:.2f} {2 * half:.2f}"

    rim = RIND + 2.5  # the rind's stroke
    xs = [CX - rim, CX + rim, *(x for x, _ in straw)]
    ys = [CY - rim, CY + rim, *(y for _, y in straw)]
    side = max(max(xs) - min(xs), max(ys) - min(ys)) + 2
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return f"{mx - side / 2:.2f} {my - side / 2:.2f} {side:.2f} {side:.2f}"


def _straw(detail: bool) -> str:
    """Drawn flat and behind the fruit, so it rises from behind the rind."""
    width, length = _STRAW["width"], _STRAW["length"]
    h, band = width / 2, width * 0.55
    edge = 1.6 if detail else 3
    return f"""
  <g transform="translate({_pt(_polar(_STRAW['at'], RIND - _STRAW['inset']))}) rotate({_STRAW['turn']})">
    <defs>
      <pattern id="stripes" patternUnits="userSpaceOnUse" width="{2 * band:.2f}" height="{4 * width:.2f}" patternTransform="skewX(-35)">
        <rect width="{2 * band:.2f}" height="{4 * width:.2f}" fill="#fbf6ee"/><rect width="{band:.2f}" height="{4 * width:.2f}" fill="#e0302f"/>
      </pattern>
    </defs>
    <rect x="0" y="{-h}" width="{length}" height="{width}" fill="url(#stripes)"/>
    <path d="M0 {-h} H{length} V{h} H0" stroke="#8c1d1d" stroke-width="{edge}" stroke-linejoin="round" fill="none"/>
  </g>"""


def icon(detail: bool) -> str:
    hl0, hl1 = _polar(-205, RIND - 4.5), _polar(-100, RIND - 4.5)
    texture = (
        f'<path d="{_streaks()}" stroke="#ffffff" stroke-width="1.2" stroke-linecap="round" opacity="0.18" clip-path="url(#pulp-clip)"/>'
        if detail
        else ""
    )
    zest = f'<g fill="#fff3a0" opacity="0.4">{_pores()}</g>' if detail else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_framed(detail)}">
  <defs>
    <radialGradient id="rind" cx="0.38" cy="0.32" r="0.75">
      <stop offset="0" stop-color="#ffe95e"/><stop offset="0.7" stop-color="#f9c80e"/><stop offset="1" stop-color="#d48f00"/>
    </radialGradient>
    <radialGradient id="pith" gradientUnits="userSpaceOnUse" cx="{CX}" cy="{CY}" r="{PITH}">
      <stop offset="0.9" stop-color="#fffcec"/><stop offset="1" stop-color="#f0dfa6"/>
    </radialGradient>
    <radialGradient id="pulp" gradientUnits="userSpaceOnUse" cx="{CX - 8}" cy="{CY - 10}" r="{PULP + 8}">
      <stop offset="0" stop-color="#fffbd2"/><stop offset="0.35" stop-color="#ffec6e"/><stop offset="0.8" stop-color="#ffd526"/><stop offset="1" stop-color="#f2b705"/>
    </radialGradient>
    <linearGradient id="highlight" gradientUnits="userSpaceOnUse" x1="{hl0[0]:.1f}" y1="{hl0[1]:.1f}" x2="{hl1[0]:.1f}" y2="{hl1[1]:.1f}">
      <stop offset="0" stop-color="#fff6a6" stop-opacity="0"/><stop offset="0.45" stop-color="#fff6a6" stop-opacity="0.95"/><stop offset="1" stop-color="#fff6a6" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="gloss" gradientUnits="userSpaceOnUse" cx="{CX - 34}" cy="{CY - 40}" r="72">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.45"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="rim-shade" gradientUnits="userSpaceOnUse" cx="{CX}" cy="{CY}" r="{PULP}">
      <stop offset="0.82" stop-color="#c98a00" stop-opacity="0"/><stop offset="1" stop-color="#c98a00" stop-opacity="0.3"/>
    </radialGradient>
    <clipPath id="pulp-clip"><circle cx="{CX}" cy="{CY}" r="{PULP}"/></clipPath>
    <mask id="flesh" maskUnits="userSpaceOnUse" x="-20" y="-20" width="300" height="300">
      <rect x="-20" y="-20" width="300" height="300" fill="#fff"/>{_tree(detail, "#000")}
    </mask>
    <filter id="raised" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="{1.4 if detail else 2}" stdDeviation="{1.3 if detail else 1.6}" flood-color="#9a6a00" flood-opacity="0.45"/>
    </filter>
    <filter id="drop" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#3a2a00" flood-opacity="0.32"/>
    </filter>
  </defs>
  {_straw(detail)}
  <circle cx="{CX}" cy="{CY}" r="{RIND}" fill="url(#rind)" stroke="#9a6800" stroke-width="{2.5 if detail else 5}" filter="url(#drop)"/>
  {zest}
  <path d="M{_pt(hl0)} A{RIND - 4.5} {RIND - 4.5} 0 0 1 {_pt(hl1)}" stroke="url(#highlight)" stroke-width="{3.5 if detail else 6}" stroke-linecap="round" fill="none"/>
  <circle cx="{CX}" cy="{CY}" r="{PITH}" fill="url(#pith)"/>
  <g filter="url(#raised)">
    <g mask="url(#flesh)">
      <circle cx="{CX}" cy="{CY}" r="{PULP}" fill="url(#pulp)"/>
      <circle cx="{CX}" cy="{CY}" r="{PULP}" fill="url(#rim-shade)"/>
      {texture}
    </g>
  </g>
  <circle cx="{CX}" cy="{CY}" r="{PULP}" fill="url(#gloss)"/>
</svg>
"""


if __name__ == "__main__":
    sys.stdout.write(icon({"detail": True, "tab": False}[sys.argv[1]]))
