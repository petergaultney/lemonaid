"""Which docs an event offers a lemon: the members of its packages, and the docs whose
triggers match its action.

An offer is `shadow` when the lemon's mode doesn't deliver it, so it is only logged. A
`packages` lemon is given every offer. A `classic` lemon is given only those of a
package or trigger that names a group or a lead (`lemons.SCOPES`), since the
always-loaded docs carry the rest.
"""

from collections import abc
from dataclasses import dataclass

from . import frontmatter, lemons, start, triggers


@dataclass(frozen=True)
class Offer:
    doc: frontmatter.Doc
    section: str
    source: dict  # {"package": name} or {"trigger": "kind pattern"}
    before: bool = False
    shadow: bool = False


@dataclass(frozen=True)
class Packages:
    given: tuple[str, ...]  # the packages the lemon's mode delivers
    shadow: tuple[str, ...]  # the other packages for it, which are only logged


def packages(docs: abc.Sequence[frontmatter.Doc], lemon: lemons.Lemon, mode: str) -> Packages:
    every = lemons.packages(docs, lemon)
    if mode == "packages":
        return Packages(tuple(every), ())

    given = lemons.packages(docs, lemon, scoped_only=True)
    return Packages(tuple(given), tuple(name for name in every if name not in given))


def members(
    docs: abc.Sequence[frontmatter.Doc],
    chosen: Packages,
    wanted: abc.Callable[[frontmatter.Doc, bool], bool],
) -> list[Offer]:
    """Each doc of *chosen*'s packages that *wanted* accepts, given the doc and whether
    its offer would be shadow."""
    given = start.members(docs, chosen.given)
    held = {member.doc.path for member in given}
    return [
        Offer(member.doc, "", {"package": member.package}, shadow=shadow)
        for shadow, found in (
            (False, given),
            (True, [m for m in start.members(docs, chosen.shadow) if m.doc.path not in held]),
        )
        for member in found
        if wanted(member.doc, shadow)
    ]


def triggered(
    docs: abc.Iterable[frontmatter.Doc],
    action: triggers.Action,
    lemon: lemons.Lemon,
    mode: str,
    refusable: bool,
) -> list[Offer]:
    """The docs whose triggers match *action*, by a trigger whose lemon keys match *lemon*.
    Only a call that hasn't run yet is *refusable*; elsewhere a `before` trigger gives
    its section as context."""
    return [
        Offer(
            doc,
            trigger.section,
            {"trigger": f"{trigger.kind} {trigger.pattern}"},
            trigger.before and refusable,
            shadow=mode != "packages" and not lemons.scoped(trigger.lemon),
        )
        for doc in docs
        for trigger in doc.triggers
        if triggers.matches(trigger, action) and lemons.applies(trigger.lemon, lemon)
    ]
