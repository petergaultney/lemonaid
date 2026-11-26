"""`lemonaid grove window remote`: another machine's web grove (`grove serve`) in a window of its
own.

The window shows the server's own pages, as a browser does, so they are always the server's
version: a lemon's page opens in the same window, and its `grove` link comes back. A link a page
opens in a new tab, such as a chat room or a PR, opens in the browser.
"""

import urllib.parse

import webview


def run(url: str) -> None:
    base = url if url.endswith("/") else f"{url}/"
    webview.create_window(
        f"lemon grove at {urllib.parse.urlsplit(base).hostname}",
        f"{base}grove",
        width=1200,
        height=800,
    )
    webview.start(private_mode=False)  # keeps the pages' storage: saved views, kept conversations
