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


def find_notification_polling_pattern(content: bytes, check_patched: bool = False) -> bytes | None:
    """Find the notification polling interval pattern dynamically.

    The minified variable name changes with each build, so we search for
    patterns like 'XXX=6000' that appear near 'notificationType' in the code.

    If check_patched=True, also look for already-patched 'XXX=0500' patterns.
    """
    # Look for short identifier = 6000 patterns (1-3 char identifiers)
    # Also check for =0500 (patched) if requested
    if check_patched:
        pattern = rb"[a-zA-Z][a-zA-Z0-9]{0,2}=(?:6000|0500)"
    else:
        pattern = rb"[a-zA-Z][a-zA-Z0-9]{0,2}=6000"
    matches = list(re.finditer(pattern, content))

    if not matches:
        return None

    # Find the match that's closest to 'notificationType' - that's the polling interval
    notification_marker = b"notificationType"
    marker_positions = [m.start() for m in re.finditer(notification_marker, content)]

    if not marker_positions:
        # Fallback: return the first match (less reliable)
        return matches[0].group()

    best_match = None
    best_distance = float("inf")

    for match in matches:
        pos = match.start()
        # Find distance to nearest notificationType marker
        for marker_pos in marker_positions:
            distance = abs(pos - marker_pos)
            if distance < best_distance:
                best_distance = distance
                best_match = match.group()

    # Only return if very close (within 500 bytes of the marker)
    # In practice, the correct pattern is ~74 bytes away, next closest is ~5000+
    if best_distance < 500:
        return best_match

    return None


def get_pattern_for_version(
    version: tuple[int, ...], content: bytes | None = None
) -> tuple[bytes, bytes] | None:
    """Return (original, patched) pattern for the given version.

    For v2.1.16+, patterns are found dynamically since minified names vary.
    """
    # v2.0.x used ewD=6000
    if version < (2, 1, 0):
        return (b"ewD=6000", b"ewD=0500")
    # v2.1.0-2.1.15 used spB=6000
    if version < (2, 1, 16):
        return (b"spB=6000", b"spB=0500")
    # v2.1.16+: find pattern dynamically (minified names change per build)
    if content is not None:
        original = find_notification_polling_pattern(content)
        if original:
            # Replace 6000 with 0500 in the pattern
            patched = original.replace(b"6000", b"0500")
            return (original, patched)
    return None


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

    content = binary_path.read_bytes()

    # For v2.1.16+, we need to check for both patched and unpatched patterns
    if version >= (2, 1, 16):
        found = find_notification_polling_pattern(content, check_patched=True)
        if found is None:
            return "unknown"
        if b"=0500" in found:
            return "patched"
        if b"=6000" in found:
            return "unpatched"
        return "unknown"

    # For older versions, use hardcoded patterns
    patterns = get_pattern_for_version(version, content)
    if patterns is None:
        return "unknown"

    original, patched = patterns

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

    content = binary_path.read_bytes()
    patterns = get_pattern_for_version(version, content)

    if patterns is None:
        return 0

    original, patched = patterns

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
