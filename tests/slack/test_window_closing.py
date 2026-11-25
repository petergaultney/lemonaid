import pytest

pytest.importorskip("webview")
pytest.importorskip("PyObjCTools")  # pywebview installs on Linux too; the window needs macOS

from lemonaid.slack import window  # noqa: E402


def test_a_save_failure_is_reported_once_and_apart_from_a_plain_close():
    saved_not = ["Signed in, but the session was not saved: locked"]

    assert window.closing([], ["waiting"], saved_not) == saved_not[0]
    assert window.closing([], ["waiting"], []) == (
        "Closed before signing in; nothing saved. Last status: waiting"
    )
    assert window.closing([], [], []) == "Closed before signing in; nothing saved"
    assert window.closing(["Signed in as sam"], [], []) == "Signed in as sam"
