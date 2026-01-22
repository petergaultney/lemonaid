"""Patch Claude Code binary to reduce notification polling delay.

Claude Code has a hardcoded 6-second polling interval for notifications,
causing ~10 second delays before notification hooks fire. This module
patches the binary to reduce that to 500ms.

See: https://github.com/anthropics/claude-code/issues/5186
"""

import platform
import re
import shutil
import subprocess
from pathlib import Path


def parse_version(name: str) -> tuple[int, ...] | None:
    """Parse version string like '2.1.15' into tuple (2, 1, 15)."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", name)
    if match:
        return tuple(int(x) for x in match.groups())
    return None


def get_pattern_for_version(version: tuple[int, ...]) -> tuple[bytes, bytes]:
    """Return (original, patched) pattern for the given version."""
    # v2.0.x used ewD=6000
    if version < (2, 1, 0):
        return (b"ewD=6000", b"ewD=0500")
    # v2.1.0+ uses spB=6000
    return (b"spB=6000", b"spB=0500")


def find_binary() -> Path | None:
    """Find the Claude Code binary. Returns the latest version."""
    home = Path.home()
    system = platform.system()

    if system == "Darwin":
        search_dirs = [
            home / "Library" / "Application Support" / "claude" / "versions",
            home / ".local" / "share" / "claude" / "versions",
        ]
    elif system == "Linux":
        search_dirs = [
            home / ".local" / "share" / "claude" / "versions",
            home / ".claude" / "versions",
        ]
    else:
        return None

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        # Find latest version (files named like 2.1.15)
        candidates = [
            f
            for f in search_dir.iterdir()
            if f.is_file() and ".backup" not in f.name and f.stat().st_mode & 0o111
        ]
        if candidates:
            # Sort by version number
            candidates.sort(key=lambda p: _version_key(p.name), reverse=True)
            return candidates[0]

    # Fallback: check PATH
    claude_path = shutil.which("claude")
    if claude_path:
        p = Path(claude_path)
        if p.is_symlink():
            p = p.resolve()
        return p

    return None


def _version_key(name: str) -> tuple[int, ...]:
    """Extract version numbers for sorting."""
    return parse_version(name) or (0,)


def check_status(binary_path: Path) -> str:
    """Check if binary is 'patched', 'unpatched', or 'unknown'."""
    version = parse_version(binary_path.name)
    if not version:
        return "unknown"

    original, patched = get_pattern_for_version(version)
    content = binary_path.read_bytes()

    if patched in content:
        return "patched"
    elif original in content:
        return "unpatched"
    else:
        return "unknown"


def apply_patch(binary_path: Path, backup: bool = True) -> int:
    """Patch the binary. Returns number of locations patched."""
    version = parse_version(binary_path.name)
    if not version:
        return 0

    original, patched = get_pattern_for_version(version)
    content = binary_path.read_bytes()

    # Find all occurrences
    count = content.count(original)
    if count == 0:
        return 0

    # Backup first
    if backup:
        backup_path = binary_path.with_suffix(binary_path.suffix + ".backup")
        if not backup_path.exists():
            shutil.copy2(binary_path, backup_path)

    # Apply patch
    patched_content = content.replace(original, patched)
    binary_path.write_bytes(patched_content)

    # Re-sign on macOS (Gatekeeper invalidates unsigned/modified binaries)
    if platform.system() == "Darwin":
        subprocess.run(
            ["codesign", "--sign", "-", "--force", str(binary_path)],
            check=True,
        )

    return count


def restore_backup(binary_path: Path) -> bool:
    """Restore from backup. Returns True if successful."""
    backup_path = binary_path.with_suffix(binary_path.suffix + ".backup")
    if not backup_path.exists():
        return False
    shutil.copy2(backup_path, binary_path)
    return True
