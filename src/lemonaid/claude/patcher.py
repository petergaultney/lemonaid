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


def _find_near_notification_type(content: bytes, check_patched: bool = False) -> bytes | None:
    """Search for XXX=6000 within 500 bytes of 'notificationType'."""
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
        return None

    best_match = None
    best_distance = float("inf")
    for match in matches:
        for marker_pos in marker_positions:
            distance = abs(match.start() - marker_pos)
            if distance < best_distance:
                best_distance = distance
                best_match = match.group()

    # Only return if very close (within 500 bytes of the marker)
    # In practice, the correct pattern is ~74 bytes away, next closest is ~5000+
    if best_distance < 500:
        return best_match
    return None


def _find_trio_pattern(content: bytes, check_patched: bool = False) -> bytes | None:
    """Find the hook module's constant trio (600000, 30000, 6000)."""
    if check_patched:
        trio = re.search(
            rb"=600000,([a-zA-Z][a-zA-Z0-9_$]*)=30000,"
            rb"([a-zA-Z][a-zA-Z0-9_$]*)=(?:6000| 500)(?![0-9])",
            content,
        )
    else:
        trio = re.search(
            rb"=600000,([a-zA-Z][a-zA-Z0-9_$]*)=30000,"
            rb"([a-zA-Z][a-zA-Z0-9_$]*)=6000(?![0-9])",
            content,
        )
    if trio is None:
        return None

    var_name = trio.group(2)
    value_start = trio.start(2) + len(var_name) + 1  # after '='
    value = content[value_start : value_start + 4]
    return var_name + b"=" + value


def find_notification_polling_pattern(content: bytes, check_patched: bool = False) -> bytes | None:
    """Find the notification polling interval pattern dynamically.

    Tries proximity to 'notificationType' first (worked on earlier builds),
    then falls back to the hook module's constant trio (600000, 30000, 6000).
    """
    return _find_near_notification_type(content, check_patched) or _find_trio_pattern(
        content, check_patched
    )


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
        # Try proximity to notificationType first (bytecode context, 0500 is safe)
        original = _find_near_notification_type(content)
        if original:
            return (original, original.replace(b"6000", b"0500"))
        # Fall back to the constant trio (readable source, strict mode —
        # 0500 is an octal literal which strict mode forbids)
        original = _find_trio_pattern(content)
        if original:
            return (original, original.replace(b"6000", b" 500"))
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
        if b"=0500" in found or b"= 500" in found:
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
