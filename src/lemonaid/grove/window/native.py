"""The macOS side of the grove window: cover the terminal it was summoned over, or put it back
where it was left, and give the terminal its focus back. Every function here runs on the main thread.
"""

import os
from collections import abc
from typing import Any

import Quartz
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationDidChangeScreenParametersNotification,
    NSEvent,
    NSEventMaskLeftMouseDragged,
    NSEventTrackingRunLoopMode,
    NSNotificationCenter,
    NSScreen,
    NSWindowDidEndLiveResizeNotification,
    NSWindowDidMoveNotification,
    NSWorkspace,
)
from Foundation import NSDate, NSMakePoint, NSMakeRect


def front_app() -> Any:
    """The app in front, or None when that's the window's own process, which is never the terminal."""
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return None if app and app.processIdentifier() == os.getpid() else app


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


def terminal_frame(app: Any) -> list[float] | None:
    """*app*'s front window as AppKit places windows, from the bottom left of the main screen."""
    found = _front_window(app.processIdentifier()) if app else None
    if not found:
        return None

    x, y, w, h = found
    return [x, NSScreen.screens()[0].frame().size.height - (y + h), w, h]


def cover(window: Any, app: Any) -> str:
    """Place *window* over *app*'s front window, or over the screen when it has none; says which."""
    found = terminal_frame(app)
    if found:
        window.setFrame_display_(NSMakeRect(*found), True)
        x, y, w, h = found
        return f"{app.localizedName()}'s window at {x:.0f},{y:.0f} {w:.0f}x{h:.0f}"

    frame = NSScreen.mainScreen().visibleFrame()
    window.setFrame_display_(frame, True)
    name = app.localizedName() if app else "no app"
    return (
        f"the screen ({name} has no window found) at {frame.size.width:.0f}x{frame.size.height:.0f}"
    )


def displays() -> str:
    """The connected displays and how they're arranged, as the key for where the window was left:
    each by vendor, model and serial number, which stay the same across restarts and reconnecting,
    and its place and size, so the same displays arranged differently are another layout."""

    def one(screen: Any) -> str:
        number, frame = screen.deviceDescription()["NSScreenNumber"], screen.frame()
        made = "-".join(
            str(made(number))
            for made in (
                Quartz.CGDisplayVendorNumber,
                Quartz.CGDisplayModelNumber,
                Quartz.CGDisplaySerialNumber,
            )
        )
        x, y, w, h = frame.origin.x, frame.origin.y, frame.size.width, frame.size.height
        return f"{made}@{x:.0f},{y:.0f},{w:.0f}x{h:.0f}"

    return " ".join(sorted(one(screen) for screen in NSScreen.screens()))


def frame_of(window: Any) -> list[float]:
    """(x, y, w, h), as AppKit places windows: from the bottom left of the main screen."""
    frame = window.frame()
    return [frame.origin.x, frame.origin.y, frame.size.width, frame.size.height]


def put(window: Any, placed: abc.Sequence[float]) -> None:
    window.setFrame_display_(NSMakeRect(*placed), True)


def drag(window: Any) -> None:
    """Move *window* with the pointer until the button is let go. It follows the pointer's place on
    the screen, in the one coordinate system that spans every display, rather than its place in the
    page, which shifts as the window moves and made a page-driven drag jitter."""
    if not NSEvent.pressedMouseButtons() & 1:
        return

    start, origin = NSEvent.mouseLocation(), window.frame().origin
    me = NSApplication.sharedApplication()
    while NSEvent.pressedMouseButtons() & 1:
        me.nextEventMatchingMask_untilDate_inMode_dequeue_(
            NSEventMaskLeftMouseDragged,
            NSDate.dateWithTimeIntervalSinceNow_(0.05),
            NSEventTrackingRunLoopMode,
            True,
        )
        now = NSEvent.mouseLocation()
        window.setFrameOrigin_(NSMakePoint(origin.x + now.x - start.x, origin.y + now.y - start.y))


def on_displays_changed(then: abc.Callable[[], None]) -> None:
    NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
        NSApplicationDidChangeScreenParametersNotification, None, None, lambda _note: then()
    )


def on_moved(window: Any, then: abc.Callable[[], None]) -> None:
    for name in (NSWindowDidMoveNotification, NSWindowDidEndLiveResizeNotification):
        NSNotificationCenter.defaultCenter().addObserverForName_object_queue_usingBlock_(
            name, window, None, lambda _note: then()
        )


def raise_(window: Any) -> None:
    window.makeKeyAndOrderFront_(None)
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def _yield_to(app: Any) -> None:
    """Yielding before activating *app* is what macOS 14's cooperative activation allows."""
    me = NSApplication.sharedApplication()
    if app and hasattr(me, "yieldActivationToApplication_"):
        me.yieldActivationToApplication_(app)


def focus(app: Any) -> None:
    _yield_to(app)
    if app:
        app.activateWithOptions_(0)


def hand_back(window: Any, app: Any) -> None:
    _yield_to(app)
    window.orderOut_(None)
    if app:
        app.activateWithOptions_(0)
