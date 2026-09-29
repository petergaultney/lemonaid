"""Check a Claude binary's patch status in a child Python process.

The check runs regexes over a ~180MB binary, and CPython's re module holds the
GIL for the whole scan, so running it on a thread stalls the Textual event
loop. A plain child process has its own GIL. It is not a multiprocessing pool:
that starts multiprocessing's resource tracker and names POSIX semaphores, and
under Textual, whose `sys.stderr` has no file descriptor, starting the tracker
fails.
"""

import asyncio
import sys
from pathlib import Path

from ..log import get_logger
from .patcher import check_status

_log = get_logger("claude.patch_status")


async def check_status_in_child(binary: Path, timeout: float = 10.0) -> str:
    """'patched', 'unpatched' or 'unknown'; a failed or slow child is logged and gives 'unknown'."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        __name__,
        str(binary),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        _log.warning("patch status check of %s timed out after %ss", binary, timeout)
        return "unknown"

    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()

    status = stdout.decode().strip()
    if proc.returncode != 0 or status not in ("patched", "unpatched", "unknown"):
        _log.warning(
            "patch status check of %s exited %s: %s",
            binary,
            proc.returncode,
            stderr.decode().strip(),
        )
        return "unknown"

    return status


if __name__ == "__main__":
    print(check_status(Path(sys.argv[1])))
