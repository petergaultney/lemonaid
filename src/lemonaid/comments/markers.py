"""Finding anchor markers in a file's body, and pairing opening and closing markers into
anchors. Each kind says how its markers are spelled and what removing one removes."""

from . import kinds, model


def find(text: str, body_scan: str, kind: kinds.Kind) -> tuple[model.Marker, ...]:
    """Markers in `body_scan`, the body with its code masked, with carriers measured in
    `text`."""
    body_end = len(body_scan)
    found = []
    for m in kind.marker_pattern().finditer(body_scan):
        if m.group("id") == model.SECTION_NAME:
            continue
        carrier = kind.marker_carrier(text, m, body_end)
        if carrier is not None:
            found.append(model.Marker(m.group("id"), bool(m.group("close")), carrier))
    return tuple(found)


def pair(
    text: str, markers: tuple[model.Marker, ...], body_end: int, kind: kinds.Kind
) -> tuple[tuple[model.Anchor, ...], list[model.ParseError]]:
    openings: dict[str, tuple[int, int]] = {}
    closings: dict[str, tuple[int, int]] = {}
    errors: list[model.ParseError] = []

    for marker in markers:
        position = marker.carrier[0]
        if marker.closing:
            if marker.id in closings:
                errors.append(_error(position, f"anchor {marker.id} is closed twice"))
            elif marker.id not in openings:
                errors.append(_error(position, f"anchor {marker.id} closes before it opens"))
            else:
                closings[marker.id] = marker.carrier
        elif marker.id in openings:
            errors.append(_error(position, f"anchor {marker.id} opens twice"))
        else:
            openings[marker.id] = marker.carrier

    anchors = []
    for anchor_id, opening in openings.items():
        closing = closings.get(anchor_id)
        start = opening[1]
        if closing is not None:
            end = max(start, closing[0])
        else:
            end = kind.point_end(text, start, body_end)
        anchors.append(model.Anchor(anchor_id, start, end, opening, closing))

    return tuple(sorted(anchors, key=lambda a: a.start)), errors


def _error(offset: int, message: str) -> model.ParseError:
    return model.ParseError(offset, message, "anchor")
