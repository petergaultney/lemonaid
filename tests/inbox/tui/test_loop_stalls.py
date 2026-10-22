"""The inbox's event loop never waits on a slow subprocess.

Every subprocess the app starts here runs `sleep` for `_SLOW_SECONDS` instead, so
a call made on the loop thread stalls it past `_STALL_SECONDS` on any machine,
however fast the real `ps`, `lsof`, `git` or `gh` would have been.
"""

import asyncio
import subprocess
import threading
import time
import traceback

import pytest

from lemonaid.inbox import db, presence
from lemonaid.inbox.tui import app as tui_app

_SLOW_SECONDS = 0.25
_STALL_SECONDS = 0.1
_REAL_MARKS = presence.Probe.marks
_REAL_POPEN = subprocess.Popen

# One tmux command each, answered by the server from memory in a few milliseconds.
# They run as `true` so the stall check still covers the rest of the loop.
_ALLOWED_ON_LOOP = frozenset(
    {
        "tmux.scratch_autosave.install_guards",
        "tmux.navigation.focused_ttys",
        "inbox.tui.watchers.focus.pane_receives_keys",
        "tmux.scratch_autosave._sample",
    }
)


def _callers() -> list[str]:
    """`module.function` of each lemonaid frame on the stack, innermost first."""
    return [
        f"{frame.filename.rsplit('/lemonaid/', 1)[-1].removesuffix('.py').replace('/', '.')}"
        f".{frame.name}"
        for frame in reversed(traceback.extract_stack())
        if "/src/lemonaid/" in frame.filename
    ]


class _SlowProcess(_REAL_POPEN):
    blocked: list[str] = []
    loop_thread: int | None = None

    def __init__(self, args, *rest, **options):
        callers = _callers()
        on_loop = threading.get_ident() == _SlowProcess.loop_thread
        allowed = on_loop and not _ALLOWED_ON_LOOP.isdisjoint(callers[:2])
        if on_loop and callers and not allowed:  # an asyncio subprocess has no lemonaid caller
            _SlowProcess.blocked.append(f"{' '.join(args)!r} from {' <- '.join(callers[:4])}")
        command = ["true"] if allowed else ["sleep", str(_SLOW_SECONDS)]
        super().__init__(command, *rest, **options)


async def _worst_gap(seconds: float) -> float:
    worst = 0.0
    last = time.monotonic()
    end = last + seconds
    while last < end:
        await asyncio.sleep(0.01)
        now = time.monotonic()
        worst = max(worst, now - last)
        last = now
    return worst


@pytest.mark.parametrize("scratch", [False, True], ids=["inbox", "scratch"])
def test_the_inbox_never_waits_on_a_subprocess(monkeypatch, tmp_path, scratch):
    monkeypatch.setattr(presence.Probe, "marks", _REAL_MARKS)
    monkeypatch.setattr(presence, "_TTL_SECONDS", 0.3)  # several listings while we watch
    monkeypatch.setattr(subprocess, "Popen", _SlowProcess)
    monkeypatch.setattr(tui_app, "find_binary", lambda: None)
    if scratch:
        monkeypatch.setenv("TMUX_PANE", "%9")
        (tmp_path / "config.toml").write_text("[tmux-session]\nautosave_scratch_size = true\n")
    with db.connect() as conn:
        for index in range(3):
            db.add(
                conn,
                f"claude:lemon-{index}",
                "working",
                f"lemon-{index}",
                {"cwd": str(tmp_path), "tty": f"/dev/ttys00{index}"},
            )

    async def run() -> float:
        _SlowProcess.loop_thread = threading.get_ident()
        _SlowProcess.blocked.clear()
        async with tui_app.LemonaidApp(scratch_mode=scratch).run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.5)  # startup's own gaps are not measured, but its subprocesses are
            return await _worst_gap(1.5)

    worst = asyncio.run(run())

    assert not _SlowProcess.blocked, "subprocess on the event loop:\n" + "\n".join(
        sorted(set(_SlowProcess.blocked))
    )
    assert worst < _STALL_SECONDS, f"the event loop stalled {worst * 1000:.0f} ms"
