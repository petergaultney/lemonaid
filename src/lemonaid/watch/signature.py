"""A lemon's comment signature: `FilmyBoy (Author)` on GitHub, `Filmy Boy (Author)` in Relay.

Matching also accepts the older `Author (FilmyBoy)` order, so existing documents keep working.
"""

import re
from collections import abc

ROLE_NAMES = ("Author", "Reviewer", "Parent", "Lead")

_ROLES = "|".join(ROLE_NAMES)
_NAME_FIRST = re.compile(rf"^(?P<name>[A-Za-z ]+?) \((?P<role>{_ROLES})\)$")
_ROLE_FIRST = re.compile(rf"^(?P<role>{_ROLES}) \((?P<name>[A-Za-z ]+)\)$")


def spaced(name: str) -> str:
    """`FilmyBoy` as `Filmy Boy`, so its Relay initials read as two letters."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.replace(" ", ""))


def sign(name: str, role: str, in_relay: bool = False) -> str:
    return f"{spaced(name) if in_relay else name.replace(' ', '')} ({role})"


def parse(signature: str) -> tuple[str, str] | None:
    """(name without a space, role), from either order and either spelling of the name."""
    found = _NAME_FIRST.match(signature.strip()) or _ROLE_FIRST.match(signature.strip())
    if not found:
        return None

    return found["name"].replace(" ", ""), found["role"]


def role_of(signature: str) -> str:
    return parsed[1] if (parsed := parse(signature)) else ""


def forms(signatures: abc.Iterable[str]) -> frozenset[str]:
    """Every spelling of each signature that names a role; other names are kept as given."""
    out: set[str] = set()
    for signature in signatures:
        if not (parsed := parse(signature)):
            out.add(signature)
            continue

        name, role = parsed
        out |= {f"{n} ({role})" for n in (name, spaced(name))}
        out |= {f"{role} ({n})" for n in (name, spaced(name))}

    return frozenset(out)
