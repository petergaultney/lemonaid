"""LaunchAgent management for the macOS notification watcher daemon."""

import contextlib
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LABEL = "com.lemonaid.notification-watcher"
PLIST_NAME = f"{LABEL}.plist"


def _get_launch_agents_dir() -> Path:
    """Get the user's LaunchAgents directory."""
    return Path.home() / "Library" / "LaunchAgents"


def _get_plist_path() -> Path:
    """Get the path to our LaunchAgent plist."""
    return _get_launch_agents_dir() / PLIST_NAME


def _get_log_dir() -> Path:
    """Get the directory for watcher logs."""
    from ..paths import get_log_dir

    return get_log_dir()


def _get_lemonaid_executable() -> str:
    """Get the path to the lemonaid executable."""
    # First try to find it in the same environment as this process
    lemonaid_path = shutil.which("lemonaid")
    if lemonaid_path:
        return lemonaid_path

    # Fall back to assuming it's installed via uv tool
    uv_bin = Path.home() / ".local" / "bin" / "lemonaid"
    if uv_bin.exists():
        return str(uv_bin)

    # Last resort: use the Python that's running this
    return f"{sys.executable} -m lemonaid"


def _get_watcher_script_path() -> Path:
    """Get the path to the watcher script."""
    # The watcher module is part of the lemonaid package
    return Path(__file__).parent / "watcher.py"


def _generate_plist() -> dict:
    """Generate the LaunchAgent plist configuration."""
    log_dir = _get_log_dir()

    # We run the watcher as a Python script using the same interpreter
    # that's running lemonaid
    watcher_script = _get_watcher_script_path()
    lemonaid_exec = _get_lemonaid_executable()

    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(watcher_script), "--lemonaid", lemonaid_exec],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "watcher.log"),
        "StandardErrorPath": str(log_dir / "watcher.err"),
        "EnvironmentVariables": {
            # Pass through PATH so the watcher can find lemonaid
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        },
    }


def install_watcher(start: bool = True) -> None:
    """Install the notification watcher as a LaunchAgent.

    Args:
        start: Whether to start the watcher after installing
    """
    plist_path = _get_plist_path()
    launch_agents_dir = _get_launch_agents_dir()

    # Ensure LaunchAgents directory exists
    launch_agents_dir.mkdir(parents=True, exist_ok=True)

    # Stop existing watcher if running
    if plist_path.exists():
        print("Stopping existing watcher...")
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)

    # Write plist
    plist_data = _generate_plist()
    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)
    print(f"Installed LaunchAgent: {plist_path}")

    # Show where logs will go
    log_dir = _get_log_dir()
    print(f"Logs will be written to: {log_dir}")

    if start:
        result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True)
        if result.returncode == 0:
            print("Watcher started successfully")
            _print_accessibility_instructions()
        else:
            print(f"Failed to start watcher: {result.stderr.decode()}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Watcher installed but not started. Run 'launchctl load' to start:")
        print(f"  launchctl load {plist_path}")


def _print_accessibility_instructions() -> None:
    """Print clear instructions for granting Accessibility permissions."""
    python_path = sys.executable

    print()
    print("=" * 60)
    print("ACCESSIBILITY PERMISSIONS REQUIRED")
    print("=" * 60)
    print()
    print("The watcher needs Accessibility permissions to read notifications.")
    print("macOS should prompt you automatically, but if not:")
    print()
    print("1. Open System Settings > Privacy & Security > Accessibility")
    print("2. Click the '+' button")
    print(f"3. Navigate to and add: {python_path}")
    print("4. Ensure the checkbox next to it is enabled")
    print()
    print("To verify permissions are working:")
    print("  lemonaid macos logs -f")
    print()
    print("You should see 'Watcher started. Listening for notifications...'")
    print("If you see 'Accessibility permission not granted', add the path above.")
    print()
    print("To open System Settings now, run:")
    print("  open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'")
    print("=" * 60)


def uninstall_watcher() -> None:
    """Stop and uninstall the notification watcher."""
    plist_path = _get_plist_path()

    if not plist_path.exists():
        print("Watcher is not installed")
        return

    # Stop the watcher
    result = subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    if result.returncode != 0:
        print(f"Warning: Failed to stop watcher: {result.stderr.decode()}", file=sys.stderr)

    # Remove the plist
    plist_path.unlink()
    print(f"Removed LaunchAgent: {plist_path}")
    print("Watcher uninstalled")


def watcher_status() -> None:
    """Check the status of the notification watcher daemon."""
    plist_path = _get_plist_path()

    if not plist_path.exists():
        print("Watcher is not installed")
        print("Run 'lemonaid macos install-watcher' to install")
        return

    # Check if it's running via launchctl
    result = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)

    if result.returncode == 0:
        # Parse the output to get PID and status
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 1:
            # Output format: PID\tStatus\tLabel
            # or just info about the job
            print(f"Watcher is installed: {plist_path}")
            print(f"Status: {result.stdout.strip()}")
    else:
        print(f"Watcher is installed but not running: {plist_path}")
        print("Start with: launchctl load", str(plist_path))

    # Show log locations
    log_dir = _get_log_dir()
    print(f"\nLogs: {log_dir}")


def watcher_logs(lines: int = 20, follow: bool = False) -> None:
    """Show recent logs from the watcher daemon.

    Args:
        lines: Number of lines to show
        follow: Whether to follow the log (like tail -f)
    """
    log_dir = _get_log_dir()
    log_file = log_dir / "watcher.log"
    err_file = log_dir / "watcher.err"

    if not log_file.exists() and not err_file.exists():
        print("No logs found. Is the watcher running?")
        print(f"Expected logs at: {log_dir}")
        return

    if follow:
        # Use tail -f on both log files
        cmd = ["tail", "-f"]
        if log_file.exists():
            cmd.append(str(log_file))
        if err_file.exists():
            cmd.append(str(err_file))
        with contextlib.suppress(KeyboardInterrupt):
            subprocess.run(cmd)
    else:
        # Show recent lines from both files
        if log_file.exists():
            print(f"=== {log_file} ===")
            subprocess.run(["tail", f"-{lines}", str(log_file)])

        if err_file.exists():
            print(f"\n=== {err_file} ===")
            subprocess.run(["tail", f"-{lines}", str(err_file)])
