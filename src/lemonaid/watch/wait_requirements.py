"""Which attached briefs need the unified waiter instead of legacy inbox-only waiting."""

import shlex

from ..brief import doc_table, sections, status, waiters


def needs_unified(text: str, children: bool) -> bool:
    docs = bool(doc_table.rows(text)) or any(
        s.heading.lower() == "prs" and s.body for s in sections.behavior(text)
    )
    if status.split(text).status == "done":
        return bool(doc_table.rows(text))

    for command in waiters.commands(text):
        try:
            words = shlex.split(command)
        except ValueError:
            return True
        if words[:3] != ["lemonaid", "inbox", "watch"]:
            return True
    return docs or children
