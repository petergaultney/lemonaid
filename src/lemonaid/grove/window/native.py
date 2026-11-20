"""The macOS side of the grove window: cover the terminal it was summoned over, and give the
terminal its focus back. Every function here runs on the main thread.
"""

from typing import Any

import Quartz
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSScreen,
    NSWorkspace,
)
from Foundation import NSMakeRect


def front_app() -> Any:
    return NSWorkspace.sharedWorkspace().frontmostApplication()


def _front_window(pid: int) -> tuple[float, float, float, float] | None:
    """*pid*'s frontmost ordinary window, (x, y, w, h) from the top left of the main screen.
    Window bounds need no Accessibility or Screen Recording permission; titles would.
    """
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    for info in windows:  # front to back
        bounds = info["kCGWindowBounds"]
        if (
            info.get("kCGWindowOwnerPID") == pid
            and info.get("kCGWindowLayer") == 0
            and min(bounds["Width"], bounds["Height"]) > 200
        ):
            return bounds["X"], bounds["Y"], bounds["Width"], bounds["Height"]

    return None


def accessory() -> None:
    """No Dock icon, while still able to take the keyboard."""
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def cover(window: Any, app: Any) -> str:
    """Place *window* over *app*'s front window, or over the screen when it has none; says which."""
    found = _front_window(app.processIdentifier()) if app else None
    if found:
        x, y, w, h = found
        main_height = NSScreen.screens()[0].frame().size.height
        window.setFrame_display_(NSMakeRect(x, main_height - (y + h), w, h), True)
        return f"{app.localizedName()}'s window at {x:.0f},{y:.0f} {w:.0f}x{h:.0f}"

    frame = NSScreen.mainScreen().visibleFrame()
    window.setFrame_display_(frame, True)
    name = app.localizedName() if app else "no app"
    return (
        f"the screen ({name} has no window found) at {frame.size.width:.0f}x{frame.size.height:.0f}"
    )


def raise_(window: Any) -> None:
    window.makeKeyAndOrderFront_(None)
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def hand_back(window: Any, app: Any) -> None:
    """Hide *window* and give *app* the focus again. Yielding first is what macOS 14's
    cooperative activation allows the frontmost app to do.
    """
    me = NSApplication.sharedApplication()
    if app and hasattr(me, "yieldActivationToApplication_"):
        me.yieldActivationToApplication_(app)
    window.orderOut_(None)
    if app:
        app.activateWithOptions_(0)
