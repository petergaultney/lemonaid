"""model.Thread trees built from a parsed `model.Document`."""

import datetime as dt
from collections import abc

from . import model


def threads(doc: model.Document) -> list[model.Thread]:
    """Roots in the order their anchors appear, orphans last; replies in `at` order.

    A comment whose id an earlier record already used is left out. A comment in a cycle
    of replies has no path from a root, so no tree reaches it. `parse` reports both.
    """
    first_by_id: dict[str, model.Comment] = {}
    for comment in doc.comments:
        first_by_id.setdefault(comment.id, comment)
    usable = [c for c in doc.comments if first_by_id[c.id] is c]

    replies_by_parent: dict[str, list[model.Comment]] = {}
    for comment in sorted(usable, key=_written_order):
        if comment.re is not None:
            replies_by_parent.setdefault(comment.re, []).append(comment)
    resolved_ids = {r.resolves for r in doc.resolutions}

    def tree(root: model.Comment) -> model.Node:
        """Built bottom-up from a depth-first order, so a long chain of replies can't
        exceed the recursion limit."""
        order: list[tuple[model.Comment, bool]] = []
        stack = [(root, False)]
        while stack:
            comment, parent_resolved = stack.pop()
            resolved = parent_resolved or comment.id in resolved_ids
            order.append((comment, resolved))
            stack += [(r, resolved) for r in reversed(replies_by_parent.get(comment.id, []))]

        nodes: dict[str, model.Node] = {}
        for comment, resolved in reversed(order):
            replies = tuple(nodes[r.id] for r in replies_by_parent.get(comment.id, []))
            nodes[comment.id] = model.Node(comment=comment, replies=replies, resolved=resolved)
        return nodes[root.id]

    anchors_by_id = {a.id: a for a in doc.anchors}
    roots = [c for c in usable if c.re is None]
    anchored = sorted(
        (c for c in roots if c.id in anchors_by_id), key=lambda c: anchors_by_id[c.id].start
    )
    orphans = sorted((c for c in roots if c.id not in anchors_by_id), key=_written_order)

    return [model.Thread(anchors_by_id.get(c.id), tree(c)) for c in [*anchored, *orphans]]


def unanswered(doc: model.Document, mine: abc.Set[str]) -> list[model.Comment]:
    """Comments that wait on the reader signed `mine`: unanswered, outside resolved
    branches, by someone else, and meant for this reader. A person's comment is meant for
    every reader, and so is one that starts a thread; a lemon's reply is meant only for
    the author of the comment it answers, so two lemons answering one person don't wake
    each other.

    A comment with replies is answered even when every reply was resolved, because
    resolving a reply closes that exchange, not the question it answered.
    """
    leaves: list[tuple[model.Comment, model.Comment | None]] = []
    for thread in threads(doc):
        stack: list[tuple[model.Node, model.Comment | None]] = [(thread.root, None)]
        while stack:
            node, parent = stack.pop()
            if node.resolved:
                continue
            if not node.replies:
                leaves.append((node.comment, parent))
            stack += [(reply, node.comment) for reply in reversed(node.replies)]
    return [
        leaf
        for leaf, parent in leaves
        if leaf.author not in mine
        and (not leaf.by_lemon or parent is None or parent.author in mine)
    ]


def _written_order(comment: model.Comment) -> tuple[dt.datetime, int]:
    return model.instant(comment.at) or dt.datetime.min.replace(tzinfo=dt.UTC), comment.offset
