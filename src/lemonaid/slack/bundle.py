"""Lemonaid.app: the small bundle the sign-in window runs in, so the Dock, Cmd-Tab and the menu
bar name lemonaid rather than Python. It is unsigned: branding, not proof of who runs it.

Its executable is a script that sets `CFProcessPath` to itself before running Python, which
makes AppKit read the bundle's Info.plist although the process is Python's.
"""

import os
import plistlib
import shlex
from pathlib import Path

BUNDLE_ID = "org.pypi.lemonaid-inbox"


def _info() -> str:
    return plistlib.dumps(
        {
            "CFBundleName": "lemonaid",
            "CFBundleDisplayName": "lemonaid",
            "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleExecutable": "lemonaid",
            "CFBundlePackageType": "APPL",
            "NSHighResolutionCapable": True,
        }
    ).decode()


def _launcher(python: str) -> str:
    # -P: the terminal's directory is not on sys.path, so nothing there can stand in for lemonaid
    return (
        "#!/bin/sh\n"
        'export CFProcessPath="$0"\n'
        f'exec {shlex.quote(python)} -P -m lemonaid slack window "$@"\n'
    )


def ensure(directory: Path, python: str) -> Path:
    """Write the bundle under *directory*, running *python*, unless it is already so; its
    executable."""
    contents = directory / "Lemonaid.app" / "Contents"
    executable = contents / "MacOS" / "lemonaid"
    for path, text in ((contents / "Info.plist", _info()), (executable, _launcher(python))):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
    os.chmod(executable, 0o755)
    return executable
