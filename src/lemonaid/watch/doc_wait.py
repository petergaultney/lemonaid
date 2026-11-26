"""The waiting loops behind `lemonaid watch doc`: one doc, or every doc on an actor's list."""

import pathlib
import time
import typing as ty
from collections import abc

from . import delivery, doc_events, turns, watch_list


def _deliverer(
    deliver: delivery.Deliver, once: bool, latest_turn: turns.Turns | None = None
) -> ty.Callable[[str], bool]:
    """True if delivered. A failure ends a one-shot waiter; a long-lived one reports it and tries again.

    While the lemon is mid-turn nothing is delivered, and the next read composes one event
    from everything that arrived meanwhile.
    """

    def attempt(message: str) -> bool:
        if not turns.idle(latest_turn):
            return False

        try:
            deliver(message)
        except delivery.Failed as e:
            if once:
                raise

            print(f"{e}; retrying in the next read", flush=True)
            return False
        return True

    return attempt


def wait_doc(
    w: doc_events.DocWatch,
    deliver: delivery.Deliver,
    once: bool,
    interval: float,
    latest_turn: turns.Turns | None = None,
) -> None:
    attempt = _deliverer(deliver, once, latest_turn)
    while True:
        if doc_events.poll(w, attempt) is doc_events.Outcome.DELIVERED and once:
            return

        time.sleep(interval)


def wait_list(
    state_dir: pathlib.Path,
    list_path: pathlib.Path,
    waiter: ty.IO[str],
    me: str,
    legacy: abc.Sequence[str],
    edits: bool,
    quiet: float,
    deliver: delivery.Deliver,
    idle_expire: float,
    interval: float,
    cursor_key: str | None = None,
    latest_turn: turns.Turns | None = None,
    writer: str = "",
) -> None:
    attempt = _deliverer(deliver, once=False, latest_turn=latest_turn)
    watches: dict[str, doc_events.DocWatch] = {}
    while True:
        for doc in watch_list.expire(list_path, idle_expire) if idle_expire else []:
            print(f"expired: no event in {doc} for {int(idle_expire)}s", flush=True)
        docs = watch_list.read(list_path)
        if not docs and watch_list.release_if_empty(list_path, waiter):
            print(f"watch list {list_path} is empty", flush=True)
            return

        watches = {
            d: watches.get(d)
            or doc_events.open_watch(
                state_dir,
                pathlib.Path(d),
                me,
                legacy,
                edits,
                quiet,
                writer,
                cursor_key=cursor_key,
                latest_turn=latest_turn,
            )
            for d in docs
        }
        for d, w in watches.items():
            if doc_events.poll(w, attempt) is doc_events.Outcome.DELIVERED:
                watch_list.touch(list_path, pathlib.Path(d))
        time.sleep(interval)
