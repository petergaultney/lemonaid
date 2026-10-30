"""`waits.Waits` on kqueue (macOS and BSD): one thread wakes the loops whose sources changed.

A watched path's directory is watched too, so a file that is missing, or that an editor
replaces by renaming a new file over it, is opened again when it reappears. The directory
wakes nobody itself: other entries in it change without concerning the loop.
A directory's own events report only entries added, removed or renamed, so a directory
whose files' contents matter also has each file in it watched. Each path and pid is opened
once however many loops watch it.
"""

import dataclasses
import os
import resource
import select
import threading
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import waits

_log = get_logger("watch.kqueue_waits")

IDLE = 45.0  # under `wait_state.STALE` less the heartbeat's own minute, so an idle loop never looks deaf
_O_EVTONLY = getattr(os, "O_EVTONLY", 0x8000)  # an fd that only watches, so it holds no volume busy


def available() -> bool:
    return hasattr(select, "kqueue")


def raise_file_limit(wanted: int = 10240) -> None:
    """Each watched path costs a descriptor, and the default soft limit is 256."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    if soft < target:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))


@dataclasses.dataclass(eq=False)
class _Node:
    path: str = ""  # "" for a process
    pid: int = 0
    fd: int = -1  # -1 while the path is missing
    wakes: dict[threading.Event, int] = dataclasses.field(default_factory=dict)
    contents: int = 0  # how many loops watch the files in this directory
    helping: int = 0  # how many watched paths this directory holds
    files: dict[str, "_Node"] = dataclasses.field(default_factory=dict)
    directory: "_Node | None" = None  # for a file watched as part of its directory's contents


_VNODE_FLAGS = (
    (
        select.KQ_NOTE_WRITE
        | select.KQ_NOTE_EXTEND
        | select.KQ_NOTE_ATTRIB
        | select.KQ_NOTE_DELETE
        | select.KQ_NOTE_RENAME
        | select.KQ_NOTE_REVOKE
    )
    if available()
    else 0
)
_REPLACED = (
    (select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME | select.KQ_NOTE_REVOKE) if available() else 0
)


class Hub:
    idle = IDLE

    def __init__(self) -> None:
        self._kq = select.kqueue()
        self._lock = threading.Lock()
        self._nodes: dict[tuple[str, int], _Node] = {}
        self._by_fd: dict[int, _Node] = {}
        self._missing: set[_Node] = set()
        threading.Thread(target=self._run, name="kqueue-waits", daemon=True).start()

    def _open(self, node: _Node) -> bool:
        try:
            node.fd = os.open(node.path, _O_EVTONLY)
        except OSError:
            node.fd = -1
            self._missing.add(node)
            return False

        self._missing.discard(node)
        self._by_fd[node.fd] = node
        event = select.kevent(
            node.fd,
            select.KQ_FILTER_VNODE,
            select.KQ_EV_ADD | select.KQ_EV_CLEAR,
            _VNODE_FLAGS,
        )
        self._kq.control([event], 0)
        return True

    def _close(self, node: _Node) -> None:
        if node.fd >= 0:
            self._by_fd.pop(node.fd, None)
            os.close(node.fd)  # which also removes its kevent
            node.fd = -1

    def _refresh_files(self, directory: _Node) -> None:
        try:
            present = (
                {e.path for e in os.scandir(directory.path) if e.is_file()}
                if directory.contents
                else set()
            )
        except OSError:
            present = set()
        for gone in set(directory.files) - present:
            node = directory.files.pop(gone)
            self._close(node)
            self._missing.discard(node)
        for name in present:
            node = directory.files.setdefault(name, _Node(path=name, directory=directory))
            if node.fd < 0:  # new, or replaced since its descriptor closed
                self._open(node)
                self._missing.discard(node)  # one that vanished at once leaves the next listing

    def _attach(self, key: tuple[str, int], wake: threading.Event | None, contents: bool) -> None:
        """Watch *key* for *wake*, or with no *wake* as the directory of a watched path."""
        node = self._nodes.get(key)
        if node is None:
            node = self._nodes[key] = _Node(path=key[0], pid=key[1])
            if node.path:
                self._open(node)
            else:
                event = select.kevent(
                    node.pid,
                    select.KQ_FILTER_PROC,
                    select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                    select.KQ_NOTE_EXIT,
                )
                try:
                    self._kq.control([event], 0)
                except ProcessLookupError:
                    if wake:
                        wake.set()  # already gone
        if wake is None:
            node.helping += 1
        else:
            node.wakes[wake] = node.wakes.get(wake, 0) + 1
        if contents:
            node.contents += 1
            self._refresh_files(node)

    def _detach(self, key: tuple[str, int], wake: threading.Event | None, contents: bool) -> None:
        node = self._nodes.get(key)
        if node is None:
            return

        if contents:
            node.contents -= 1
            self._refresh_files(node)
        if wake is None:
            node.helping -= 1
        else:
            node.wakes[wake] -= 1
            if node.wakes[wake] <= 0:
                del node.wakes[wake]
        if node.wakes or node.helping > 0:
            return

        del self._nodes[key]
        self._missing.discard(node)
        self._close(node)

    def watch(
        self,
        paths: abc.Iterable[Path],
        pids: abc.Iterable[int],
        wake: threading.Event,
        contents: abc.Iterable[Path] = (),
    ) -> waits.Unwatch:
        watched = [Path(p).expanduser().absolute() for p in [*paths, *contents]]
        keys = {(str(path), 0) for path in watched} | {("", pid) for pid in pids if pid > 0}
        parents = {(str(path.parent), 0) for path in watched}
        directories = {(str(Path(d).expanduser().absolute()), 0) for d in contents}
        with self._lock:
            for key in keys:
                self._attach(key, wake, key in directories)
            for key in parents:
                self._attach(key, None, False)

        def unwatch() -> None:
            with self._lock:
                for key in keys:
                    self._detach(key, wake, key in directories)
                for key in parents:
                    self._detach(key, None, False)

        return unwatch

    def wake_all(self) -> None:
        with self._lock:
            woken = {wake for node in self._nodes.values() for wake in node.wakes}
        for wake in woken:
            wake.set()

    def _changed(self, event: "select.kevent") -> set[threading.Event]:
        if event.filter == select.KQ_FILTER_PROC:
            node = self._nodes.get(("", event.ident))
            return set(node.wakes) if node else set()

        node = self._by_fd.get(event.ident)
        if node is None:
            return set()

        if node.directory is not None:
            if event.fflags & _REPLACED:
                self._close(node)
                self._open(node)  # a replacement already in place; else the directory's refresh
                self._missing.discard(node)
            return set(node.directory.wakes)

        woken = set(node.wakes)
        if event.fflags & _REPLACED:
            self._close(node)
            self._open(node)
        if node.contents:
            self._refresh_files(node)
        for missing in [m for m in self._missing if os.path.dirname(m.path) == node.path]:
            if self._open(missing):
                woken |= set(missing.wakes)
                if missing.contents:
                    self._refresh_files(missing)
        return woken

    def _run(self) -> None:
        while True:
            try:
                events = self._kq.control(None, 64, None)
            except InterruptedError:
                continue

            woken: set[threading.Event] = set()
            with self._lock:
                for event in events:
                    try:
                        woken |= self._changed(event)
                    except OSError as error:
                        _log.warning("kqueue event %s: %s", event, error)
            for wake in woken:
                wake.set()
