#!/usr/bin/env python3
"""macOS Notification Center watcher daemon.

This script watches for notifications appearing in macOS Notification Center
using the Accessibility API, then calls `lemonaid macos notify` to add them
to the lemonaid inbox.

Requires:
- macOS
- Accessibility permissions granted
- pyobjc-framework-Quartz and pyobjc-framework-ApplicationServices

Run as a daemon via LaunchAgent (see launchd.py) or directly for testing.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

# These imports will fail if PyObjC is not installed
try:
    import objc
    from AppKit import NSWorkspace
    from ApplicationServices import (
        AXIsProcessTrustedWithOptions,
        AXObserverAddNotification,
        AXObserverCreate,
        AXObserverGetRunLoopSource,
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        kAXChildrenAttribute,
        kAXDescriptionAttribute,
        kAXSubroleAttribute,
        kAXTrustedCheckOptionPrompt,
        kAXValueAttribute,
        kAXWindowCreatedNotification,
    )
    from Foundation import CFRunLoopAddSource, CFRunLoopGetCurrent, kCFRunLoopDefaultMode
except ImportError as e:
    print(f"Error: PyObjC not installed: {e}", file=sys.stderr)
    print("Install with: pip install lemonaid[macos]", file=sys.stderr)
    sys.exit(1)


# Create the callback type for AXObserverCreate
PAXObserverCallback = objc.callbackFor(AXObserverCreate)

# Global state for the callback (callbacks can't be methods)
_watcher_state: dict[str, Any] = {
    "lemonaid_cmd": "lemonaid",
    "last_notification_time": 0,
    "debounce_seconds": 0.5,
}


def _log(msg: str) -> None:
    """Log a message with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _find_notification_center_pid() -> int | None:
    """Find the PID of the Notification Center process."""
    workspace = NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if app.bundleIdentifier() == "com.apple.notificationcenterui":
            return app.processIdentifier()

    return None


def _extract_notification_banner(element: Any) -> dict[str, Any] | None:
    """Extract notification details from an AXNotificationCenterBanner element.

    Returns dict with app_name, title, subtitle, body, ax_id if this is a real notification.
    """
    # Check if this is a notification banner (not a widget)
    err, subrole = AXUIElementCopyAttributeValue(element, kAXSubroleAttribute, None)
    if err != 0 or str(subrole) != "AXNotificationCenterBanner":
        return None

    # Get the description which contains: "AppName, Title, Subtitle, Body"
    err, description = AXUIElementCopyAttributeValue(element, kAXDescriptionAttribute, None)
    if err != 0 or not description:
        return None

    desc_str = str(description)
    _log(f"  Found banner: {desc_str[:100]}...")

    # Get the AXIdentifier (UUID) for deduplication
    err, ax_identifier = AXUIElementCopyAttributeValue(element, "AXIdentifier", None)
    ax_id = str(ax_identifier) if err == 0 and ax_identifier else None

    # Debug: dump all attribute names and actions to find URL or click action
    from ApplicationServices import AXUIElementCopyActionNames, AXUIElementCopyAttributeNames

    err, attr_names = AXUIElementCopyAttributeNames(element, None)
    if err == 0 and attr_names:
        _log(f"  Banner attributes: {list(attr_names)}")
        # Dump AXCustomActions - might contain URL or deep link info
        err, custom_actions = AXUIElementCopyAttributeValue(element, "AXCustomActions", None)
        _log(
            f"  AXCustomActions err={err}, value={custom_actions}, type={type(custom_actions).__name__ if custom_actions else None}"
        )
        if err == 0 and custom_actions:
            for i, action in enumerate(custom_actions):
                _log(f"    Action {i}: {action} (type: {type(action).__name__})")
                # Try to get action properties
                if hasattr(action, "allKeys"):
                    for key in action.allKeys():
                        _log(f"      {key}: {action[key]}")

    err, action_names = AXUIElementCopyActionNames(element, None)
    if err == 0 and action_names:
        _log(f"  Banner actions: {list(action_names)}")

    # Parse description - first element is the app name
    parts = desc_str.split(", ", 1)
    app_name = parts[0] if parts else "unknown"

    # Get the detailed fields from children (they have AXIdentifier: title, subtitle, body)
    title = ""
    subtitle = ""
    body = ""

    err, children = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute, None)
    if err == 0 and children:
        for child in children:
            err, identifier = AXUIElementCopyAttributeValue(child, "AXIdentifier", None)
            err2, value = AXUIElementCopyAttributeValue(child, kAXValueAttribute, None)
            if err == 0 and err2 == 0 and identifier and value:
                id_str = str(identifier)
                val_str = str(value)
                if id_str == "title":
                    title = val_str
                elif id_str == "subtitle":
                    subtitle = val_str
                elif id_str == "body":
                    body = val_str

    return {
        "app_name": app_name,
        "title": title,
        "subtitle": subtitle,
        "body": body,
        "description": desc_str,
        "ax_id": ax_id,
    }


def _find_notification_banners(window_element: Any) -> list[dict[str, Any]]:
    """Traverse the notification center window to find notification banners.

    Only returns actual notifications (AXNotificationCenterBanner), not widgets.
    """
    notifications = []

    def traverse(element: Any, depth: int = 0) -> None:
        if depth > 10:
            return

        # Check if this element is a notification banner
        banner = _extract_notification_banner(element)
        if banner:
            notifications.append(banner)
            return  # Don't traverse into banner children, we already extracted them

        # Traverse children
        err, children = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute, None)
        if err == 0 and children:
            for child in children:
                traverse(child, depth + 1)

    traverse(window_element)
    return notifications


def _send_notification(
    lemonaid_cmd: str,
    app_bundle_id: str,
    title: str,
    body: str,
    workspace: str | None = None,
    ax_id: str | None = None,
) -> None:
    """Send a notification to lemonaid."""
    cmd = f"{lemonaid_cmd} macos notify --app {shlex.quote(app_bundle_id)} --title {shlex.quote(title)} --body {shlex.quote(body)}"
    if workspace:
        cmd += f" --workspace {shlex.quote(workspace)}"
    if ax_id:
        cmd += f" --ax-id {shlex.quote(ax_id)}"
    _log(f"Calling: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            _log(f"Error from lemonaid: {result.stderr}")
    except subprocess.TimeoutExpired:
        _log("Timeout calling lemonaid")
    except Exception as e:
        _log(f"Exception calling lemonaid: {e}")


@PAXObserverCallback
def _observer_callback(observer: Any, element: Any, notification: Any, refcon: Any) -> None:
    """Callback when a notification center event occurs."""
    now = time.time()

    # Debounce - notification center can fire multiple events quickly
    if now - _watcher_state["last_notification_time"] < _watcher_state["debounce_seconds"]:
        return

    _watcher_state["last_notification_time"] = now

    _log(f"Notification event: {notification}")

    # Find actual notification banners (not widgets)
    banners = _find_notification_banners(element)

    for banner in banners:
        app_name = banner["app_name"]
        title = banner["title"]
        subtitle = banner["subtitle"]
        body = banner["body"]
        ax_id = banner.get("ax_id")

        _log(
            f"  Notification from {app_name}: title={title}, subtitle={subtitle}, body={body[:50] if body else ''}..."
        )

        # Map app name to bundle ID for filtering (Slack → com.tinyspeck.slackmacgap)
        bundle_id = "com.tinyspeck.slackmacgap" if app_name.lower() == "slack" else app_name.lower()

        # For Slack: title=workspace, subtitle=channel, body=message
        # Pass workspace separately for multi-workspace deep linking
        workspace = title if app_name.lower() == "slack" else None
        display_title = subtitle if subtitle else title  # Channel or sender name
        display_body = body if body else ""

        if display_title or display_body:
            _send_notification(
                _watcher_state["lemonaid_cmd"],
                bundle_id,
                display_title,
                display_body,
                workspace=workspace,
                ax_id=ax_id,
            )

    if not banners:
        _log("  No notification banners found (may be widgets only)")


def start_watcher(lemonaid_cmd: str) -> None:
    """Start watching for notifications."""
    _watcher_state["lemonaid_cmd"] = lemonaid_cmd

    _log("Starting notification watcher...")

    trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    if not trusted:
        _log("Accessibility permission not granted. Please enable in System Settings.")
        _log("System Settings > Privacy & Security > Accessibility")

    nc_pid = _find_notification_center_pid()
    if not nc_pid:
        _log("ERROR: Could not find Notification Center process")
        sys.exit(1)

    _log(f"Found Notification Center PID: {nc_pid}")

    nc_element = AXUIElementCreateApplication(nc_pid)

    # Debug: scan existing windows/notifications on startup
    _log("Scanning existing notifications...")
    err, windows = AXUIElementCopyAttributeValue(nc_element, "AXWindows", None)
    if err == 0 and windows:
        _log(f"  Found {len(windows)} windows")
        for window in windows:
            banners = _find_notification_banners(window)
            _log(f"  Window has {len(banners)} banners")
    else:
        _log("  No windows found (or error)")

    err, observer = AXObserverCreate(nc_pid, _observer_callback, None)
    if err != 0:
        _log(f"ERROR: Failed to create observer (error {err})")
        _log("This usually means accessibility permissions are not granted.")
        sys.exit(1)

    err = AXObserverAddNotification(observer, nc_element, kAXWindowCreatedNotification, None)
    if err != 0:
        _log(f"WARNING: Failed to add window created notification (error {err})")

    run_loop_source = AXObserverGetRunLoopSource(observer)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), run_loop_source, kCFRunLoopDefaultMode)

    _log("Watcher started. Listening for notifications...")
    _log(f"Will call: {lemonaid_cmd} macos notify ...")

    try:
        from Foundation import NSRunLoop

        run_loop = NSRunLoop.currentRunLoop()
        while True:
            run_loop.runUntilDate_(
                NSRunLoop.currentRunLoop().limitDateForMode_(kCFRunLoopDefaultMode)
            )
    except KeyboardInterrupt:
        _log("Shutting down...")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch macOS Notification Center and forward to lemonaid"
    )
    parser.add_argument(
        "--lemonaid",
        default="lemonaid",
        help="Path to lemonaid executable (default: lemonaid)",
    )
    args = parser.parse_args()

    start_watcher(args.lemonaid)


if __name__ == "__main__":
    main()
