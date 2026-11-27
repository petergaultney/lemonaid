"""The process model and framing every kind of plugin shares."""

import time

import pytest

from lemonaid.plugins import running

from ..doc_plugins.shared import fake

_HELLO = b"lemonaid-doc-plugin 1"


def test_notices_pass_on_before_an_answer_and_between_requests():
    seen: list[str] = []
    plugin = running.Running(fake("--notice"), _HELLO, 5, on_notice=seen.append)
    try:
        assert plugin.ask("body /n.md", [], "a\n%% Sam: x\nb\n") == "a\nb\n"
        assert seen == ["ready hello", "ready body"]
        plugin.read_notices(0.1)
        assert seen == ["ready hello", "ready body"]  # nothing more came
    finally:
        plugin.close()


def test_a_plugin_gets_the_environment_it_is_given():
    plugin = running.Running(fake("--echo-env", "MY_VAR"), _HELLO, 5, env={"MY_VAR": "here"})
    try:
        assert plugin.ask("body /n.md", [("name", "Ana")], "") == "here"
    finally:
        plugin.close()


def test_a_wrong_hello_or_a_slow_answer_fails():
    with pytest.raises(running.Failed, match="not 'lemonaid-source-plugin 1'"):
        running.Running(fake(), b"lemonaid-source-plugin 1", 5)

    plugin = running.Running(fake("--hang"), _HELLO, 0.2)
    try:
        with pytest.raises(running.Failed, match="timed out"):
            plugin.ask("body /n.md", [], "x")
    finally:
        plugin.close()


def test_a_request_line_with_a_line_break_is_refused():
    plugin = running.Running(fake(), _HELLO, 5)
    try:
        with pytest.raises(running.Failed, match="line break"):
            plugin.ask("body /a\nb.md", [], "x")
    finally:
        plugin.close()


def test_a_plugin_that_stops_reading_fails_the_request_at_its_deadline():
    plugin = running.Running(fake("--deaf"), _HELLO, 0.3)
    started = time.monotonic()
    try:
        with pytest.raises(running.Failed, match="timed out writing"):
            plugin.ask("body /n.md", [], "x" * (4 << 20))  # far more than a pipe holds
    finally:
        plugin.close()

    assert time.monotonic() - started < 3  # the request's deadline, and close's one second
