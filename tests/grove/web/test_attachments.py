"""Files a browser attaches to a message: how they are kept, found again, and handed on."""

import base64
import os
import time

from lemonaid.grove.web import attachments


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_a_saved_file_is_found_by_its_id_under_a_safe_name():
    saved = attachments.save("../../etc/pass wd?.txt", "text/plain", _b64(b"hello"))

    assert isinstance(saved, dict)
    assert (saved["name"], saved["size"], saved["mime"]) == ("pass wd_.txt", 5, "text/plain")
    [found] = attachments.found([saved["id"]])
    assert found.path.read_bytes() == b"hello"
    assert found.path.parent.parent == attachments._root()
    assert found.mime == "text/plain"


def test_names_lose_what_could_hide_or_escape_them():
    assert attachments.safe_name("C:\\Users\\ada\\photo.JPG") == "photo.JPG"
    assert attachments.safe_name(".hidden") == "hidden"
    assert attachments.safe_name("...") == "file"
    long = attachments.safe_name("a" * 300 + ".pdf")
    assert len(long) == 100 and long.endswith(".pdf")


def test_what_cant_be_kept_is_refused_in_words(monkeypatch):
    monkeypatch.setattr(attachments, "MAX_BYTES", 4)

    assert attachments.save("big.bin", "", _b64(b"12345")) == "big.bin is larger than 0 MB"
    assert attachments.save("none.txt", "", "") == "none.txt is empty"
    assert attachments.save("bad.txt", "", "not base64!") == "the file didn't arrive whole"


def test_an_id_that_names_nothing_kept_is_refused():
    assert attachments.found(["../../secrets"]) == (
        "an attachment is gone from the server; remove it and attach it again"
    )
    assert attachments.found(["20261126-120000-0123abcd"]) == (
        "an attachment is gone from the server; remove it and attach it again"
    )
    many = [attachments.save(f"{n}.txt", "", _b64(b"x"))["id"] for n in range(11)]
    assert attachments.found(many) == "a message takes at most 10 files"


def test_a_dropped_file_is_gone():
    saved = attachments.save("a.txt", "", _b64(b"x"))

    assert attachments.drop(saved["id"]) == ""
    assert isinstance(attachments.found([saved["id"]]), str)


def test_old_files_go_at_the_next_upload():
    old = attachments.save("old.txt", "", _b64(b"x"))
    folder = attachments._root() / old["id"]
    long_ago = time.time() - (attachments.KEEP_DAYS + 1) * 86400
    os.utime(folder, (long_ago, long_ago))

    attachments.save("new.txt", "", _b64(b"y"))

    assert not folder.exists()


def test_a_terminal_lemon_gets_the_paths_after_the_text():
    one = attachments.found([attachments.save("a.png", "image/png", _b64(b"x"))["id"]])
    assert isinstance(one, list)

    assert attachments.as_text("look", one) == f"look\n\nAttached file:\n- {one[0].path}"
    assert attachments.as_text("", one) == f"Attached file:\n- {one[0].path}"
    assert attachments.as_text("just words", []) == "just words"


def test_a_chat_gets_the_files_themselves():
    found = attachments.found(
        [
            attachments.save("a.png", "image/png", _b64(b"png"))["id"],
            attachments.save("b.pdf", "application/pdf", _b64(b"pdf"))["id"],
        ]
    )
    assert isinstance(found, list)

    assert attachments.for_chat(found) == [
        {"type": "image", "mimeType": "image/png", "fileName": "a.png", "content": _b64(b"png")},
        {
            "type": "file",
            "mimeType": "application/pdf",
            "fileName": "b.pdf",
            "content": _b64(b"pdf"),
        },
    ]
