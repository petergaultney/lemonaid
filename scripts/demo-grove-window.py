#!/usr/bin/env python3
"""Screenshot the grove window (macOS) showing the demo grove of invented lemons.

    uv run --extra web scripts/demo-grove-window.py docs/images/grove-window.png

Stages the same grove as `demo-grove.py`, runs the window against the demo's own state
directory, summons it at a fixed size, and has WebKit write out what the window shows, so the
picture holds nothing from the screen. The window flashes over a corner of it for a few seconds.

`--serve` is the window itself, which the script starts for you.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("demo_grove", HERE / "demo-grove.py")
assert _spec and _spec.loader
grove = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grove)  # points every LEMONAID_* variable at the demo's scratch directory

from lemonaid.grove.window import control  # noqa: E402

_WIDTH, _HEIGHT = 1500, 950  # points; the PNG is twice that on a Retina screen
_SETTLE_SECONDS = 6  # for the window to load the grove and draw it


def _snapshot(output: Path) -> None:
    """Write the window's web view to *output* as a PNG, drawn by WebKit itself rather than
    captured from the screen, so it needs no Screen Recording permission."""
    import threading

    import webview
    from AppKit import NSBitmapImageRep, NSPNGFileType
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    done = threading.Event()

    def take() -> None:
        try:
            _take()
        except Exception as error:  # reported here, since the main thread's exceptions vanish
            print(f"snapshot failed: {error!r}", file=sys.stderr)
            done.set()

    def _take() -> None:
        web_view = BrowserView.instances[webview.windows[0].uid].webview

        def written(image, error) -> None:
            if image is None:
                print(f"snapshot failed: {error}", file=sys.stderr)
            else:
                rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
                output.write_bytes(
                    bytes(rep.representationUsingType_properties_(NSPNGFileType, None))
                )
            done.set()

        web_view.takeSnapshotWithConfiguration_completionHandler_(None, written)

    AppHelper.callAfter(take)
    done.wait(30)


def _serve(output: Path) -> None:
    """Run the window, summon it at a fixed frame, snapshot it, and exit."""
    import threading

    from AppKit import NSMakeRect  # needs the `web` extra, so not imported at the top

    from lemonaid.config import load_config
    from lemonaid.grove.window import app, native

    def cover(window, _front) -> str:
        window.setFrame_display_(NSMakeRect(60, 120, _WIDTH, _HEIGHT), True)
        return "a fixed frame for the screenshot"

    def capture() -> None:
        deadline = time.monotonic() + 60
        while not control.socket_path().exists() and time.monotonic() < deadline:
            time.sleep(0.5)
        time.sleep(1)
        control.send("show")
        time.sleep(_SETTLE_SECONDS)
        _snapshot(output)
        control.send("hide")
        os._exit(0)

    native.cover = cover
    threading.Thread(target=capture, daemon=True).start()
    app.run(load_config())


def _capture(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    subprocess.run([sys.executable, __file__, "--serve", str(output.resolve())], timeout=180)
    if not output.exists():
        raise SystemExit("The grove window wrote no screenshot; is the `web` extra installed?")

    print(f"wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", help="PNG to write")
    parser.add_argument("--serve", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--kill", action="store_true", help="tear down the server and its state")
    args = parser.parse_args()

    if args.serve:
        _serve(args.serve)
        return

    if args.kill:
        grove.demo._kill()
        return

    if not args.output:
        parser.error("an output PNG is required")

    grove._stage([], 232, 62)
    _capture(args.output)


if __name__ == "__main__":
    main()
