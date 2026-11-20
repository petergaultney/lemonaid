"""Records a test's Codex has stored, for the `codex_records` fixture."""

from collections import abc

from lemonaid.codex import stored, threads


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
