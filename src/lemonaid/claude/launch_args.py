"""The exact argv a running process was started with.

`ps` joins arguments with spaces, which loses the boundaries inside a `--settings` JSON
string, so this reads the kernel's copy instead.
"""

import ctypes
import ctypes.util
import struct
import sys
from pathlib import Path

_CTL_KERN, _KERN_PROCARGS2 = 1, 49


def _darwin(pid: int) -> list[str]:
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    mib = (ctypes.c_int * 3)(_CTL_KERN, _KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
        return []
    buf = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return []

    raw = buf.raw[: size.value]
    argc = struct.unpack_from("i", raw)[0]
    # After argc: the executable path, NUL padding, then argc NUL-terminated arguments.
    rest = raw[4:].split(b"\0", 1)[1].lstrip(b"\0")
    return [a.decode(errors="replace") for a in rest.split(b"\0")[:argc]]


def argv(pid: int) -> list[str]:
    """[] when the process is gone or not ours to read."""
    if sys.platform == "darwin":
        return _darwin(pid)

    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [a.decode(errors="replace") for a in raw.split(b"\0") if a]
