"""The Slack sign-in window (macOS, the `slack` extra): Slack's own sign-in pages in a web view,
run inside Lemonaid.app (see `bundle`), whose title names lemonaid and the host of whatever
page it shows. Once the page holds a token Slack accepts, it saves the session and closes.

Its web data is kept in a WebKit store of its own, so a second sign-in finds the user still
signed in, and pywebview's choice, WebKit's default store, which its private mode wipes at every
start, never holds it. Slack's Content Security Policy refuses pywebview's `evaluate_js`, which
wraps a script in `eval()`, so scripts run through WKWebView itself.
"""

import plistlib
import threading
import time
import types
import urllib.parse
import uuid

import AppKit
import Foundation
import webview
from PyObjCTools import AppHelper
from webview.platforms import cocoa

from . import api, signin

_STORE = str(uuid.uuid5(uuid.NAMESPACE_URL, "lemonaid/slack-signin")).upper()
_TITLE = "lemonaid: sign in to Slack for your lemons"
_LOOK_EVERY = 2.0
_TITLE_EVERY = 0.2

# The tokens the page holds: per team in localConfig_v2, in any localStorage value, and in the
# client's next API call. Handed to Python only, which never prints them.
_LOOK_JS = r"""
(() => {
  const token = (s) => { const m = typeof s === 'string' && s.match(/xoxc-[A-Za-z0-9-]+/); return m ? m[0] : ''; };
  const out = {teams: [], stored: [], called: window.__lemonaidToken || ''};
  try {
    const c = JSON.parse(localStorage.getItem('localConfig_v2') || 'null');
    if (c && c.teams) out.teams = Object.values(c.teams).map(t => ({token: t.token || ''}));
    for (let i = 0; i < localStorage.length; i++) {
      const t = token(localStorage.getItem(localStorage.key(i)) || '');
      if (t) out.stored.push({token: t});
    }
  } catch (e) {}
  if (!window.__lemonaidHooked) {
    window.__lemonaidHooked = true;
    const grab = (s) => { const t = token(s); if (t) window.__lemonaidToken = t; };
    const append = FormData.prototype.append;
    FormData.prototype.append = function (k, v) { if (k === 'token') grab(v); return append.apply(this, arguments); };
    const fetch0 = window.fetch;
    window.fetch = function (input, init) {
      try {
        const b = init && init.body;
        if (typeof b === 'string') grab(b);
        else if (b instanceof URLSearchParams || b instanceof FormData) grab(b.get('token'));
      } catch (e) {}
      return fetch0.apply(this, arguments);
    };
  }
  return JSON.stringify(out);
})()
"""


class _OwnStore:
    """Stands in for WKWebsiteDataStore in pywebview's Cocoa backend, giving its windows the
    store `_STORE` (macOS 14 and later) instead of WebKit's default."""

    _store = None

    @classmethod
    def defaultDataStore(cls):  # the name pywebview calls
        if cls._store is None:
            identifier = Foundation.NSUUID.alloc().initWithUUIDString_(_STORE)
            cls._store = _WEBKIT.WKWebsiteDataStore.dataStoreForIdentifier_(identifier)
        return cls._store

    @staticmethod
    def allWebsiteDataTypes():
        return _WEBKIT.WKWebsiteDataStore.allWebsiteDataTypes()


class _WebKit(types.ModuleType):
    def __getattr__(self, name: str):
        return getattr(_WEBKIT, name)


_WEBKIT = cocoa.WebKit
cocoa.WebKit = _WebKit("WebKit")
cocoa.WebKit.WKWebsiteDataStore = _OwnStore


def _user_agent() -> str:
    """Safari's, since sign-in pages check for its `Safari/` part, which WKWebView's lacks."""
    try:
        with open("/Applications/Safari.app/Contents/Info.plist", "rb") as info:
            version = plistlib.load(info)["CFBundleShortVersionString"]
    except (OSError, KeyError, plistlib.InvalidFileException):
        version = "18.0"
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        f"(KHTML, like Gecko) Version/{version} Safari/605.1.15"
    )


def title(address: str) -> str:
    url = urllib.parse.urlparse(address)
    if not url.hostname:
        return _TITLE

    return f"{_TITLE} · {url.hostname} {'🔒' if url.scheme == 'https' else '⚠️ not encrypted'}"


def _browser(window: webview.Window):
    return cocoa.BrowserView.instances[window.uid]


def _retitle(window: webview.Window, shown: list[str]) -> None:
    """On the main thread: the title for the page the view shows now."""
    browser = _browser(window)
    address = str(browser.webview.URL() or "")
    if address != shown[0]:
        shown[0] = address
        browser.window.setTitle_(title(address))


def _cookie(window: webview.Window) -> tuple[str, str] | None:
    """The `d` cookie's value and expiry, from the window's own store."""
    found: list[tuple[str, str]] = []
    done = threading.Event()

    def handler(cookies) -> None:
        found.extend(
            (str(c.value()), str(c.expiresDate()))
            for c in cookies
            if str(c.name()) == "d" and str(c.domain()).lstrip(".").endswith("slack.com")
        )
        done.set()

    store = _browser(window).webview.configuration().websiteDataStore()
    AppHelper.callAfter(store.httpCookieStore().getAllCookies_, handler)
    done.wait(10)
    return found[0] if found else None


def _lemon() -> AppKit.NSImage:
    size = 512.0
    image = AppKit.NSImage.alloc().initWithSize_((size, size))
    image.lockFocus()
    AppKit.NSAttributedString.alloc().initWithString_attributes_(
        "🍋", {AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(size * 0.8)}
    ).drawAtPoint_((size * 0.06, size * 0.02))
    image.unlockFocus()
    return image


def _wait_for_session(window: webview.Window, workspace: str, result: list[str]) -> None:
    shown = [""]
    looked = 0.0
    while window.uid in cocoa.BrowserView.instances:  # until the user closes it
        time.sleep(_TITLE_EVERY)
        AppHelper.callAfter(_retitle, window, shown)
        if time.monotonic() - looked < _LOOK_EVERY:
            continue

        looked = time.monotonic()
        look = _browser(window).evaluate_js(_LOOK_JS, True) or {}  # None mid-navigation
        candidates = signin.tokens(look) if isinstance(look, dict) else []
        cookie = _cookie(window) if candidates else None
        if not cookie:
            continue

        try:
            found = signin.capture(candidates, *cookie, workspace)
        except api.Unavailable as error:
            print(f"can't reach Slack to check the sign-in ({error}); trying again", flush=True)
            continue
        if found:
            signin.keep(found)
            result.append(f"Signed in to Slack as {found.user} on {found.team}")
            window.destroy()
            return


def run(workspace: str) -> int:
    result: list[str] = []
    window = webview.create_window(_TITLE, workspace, width=1000, height=800)

    def started() -> None:
        AppHelper.callAfter(
            lambda: AppKit.NSApplication.sharedApplication().setApplicationIconImage_(_lemon())
        )
        threading.Thread(
            target=_wait_for_session, args=(window, workspace, result), daemon=True
        ).start()

    webview.start(started, private_mode=False, user_agent=_user_agent())
    print(result[0] if result else "Closed before signing in; nothing saved")
    return 0 if result else 1
