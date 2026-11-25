"""What a test's Codex has stored, for the `codex_records` fixture, and names set in it."""

import types
from collections import abc

from lemonaid.codex import stored, thread_name, threads


def thread(
    thread_id: str,
    cwd: str = "/work",
    *,
    parent: str = "",
    path: str = "",
    name: str = "",
    updated_at: int = 0,
    archived: bool = False,
) -> stored.Thread:
    return stored.Thread(thread_id, cwd, name, "", parent, path, updated_at, archived)


class Records(dict[str, stored.Thread | None]):
    """A thread's record, or None for one Codex has no conversation for. With `everything`
    set, a thread not listed gets the record it returns; otherwise Codex can't be asked
    about it."""

    everything: abc.Callable[[str], stored.Thread | None] | None = None

    def answers(self, threads: abc.Iterable[str]) -> dict[str, stored.Thread | None]:
        return {
            t: self[t] if t in self else self.everything(t)
            for t in threads
            if t in self or self.everything is not None
        }


def answer(monkeypatch, record: abc.Callable[[str], stored.Thread | None]) -> None:
    """Have the test's Codex answer every thread with *record(thread)*."""
    monkeypatch.setattr(threads, "_ask", lambda asked: {t: record(t) for t in asked})


def server(stored: dict[str, str], sets: list[tuple[str, str]]) -> types.SimpleNamespace:
    """An app-server that stores *stored* (thread to name), knows no other thread, and adds
    each (thread, name) it is asked to set to *sets*."""

    def reply(method: str, params: dict) -> dict:
        if params["threadId"] not in stored:
            return {"error": {"message": f"thread not found: {params['threadId']}"}}

        if method == "thread/name/set":
            sets.append((params["threadId"], params["name"]))
            stored[params["threadId"]] = params["name"]
            return {"result": {}}

        return {"result": {"thread": {"name": stored[params["threadId"]] or None}}}

    return types.SimpleNamespace(
        ask=lambda calls, _timeout: [
            {"id": number, **reply(*call)} for number, call in enumerate(calls)
        ]
    )


def names_set(monkeypatch, stored: dict[str, str]) -> list[tuple[str, str]]:
    """Each (thread, name) lemonaid sets through a short-lived `server(stored, ...)`."""
    sets: list[tuple[str, str]] = []

    def once(question, _about, unanswered, _timeout):
        try:
            return question(server(stored, sets))
        except thread_name.app_server.NoAnswer:
            return unanswered

    monkeypatch.setattr(thread_name.app_server, "once", once)
    return sets
