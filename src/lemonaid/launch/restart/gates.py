"""Small adapters for existing delivery and hook entry points."""

import contextlib
import functools
import inspect
import json
import os
import sys
import time
import typing as ty
from collections import abc

from ...inbox import db
from ...inbox.channel import channel_id
from . import native, state


def exclusive(argument: str) -> abc.Callable:
    def decorate(function: abc.Callable) -> abc.Callable:
        signature = inspect.signature(function)

        @functools.wraps(function)
        def call(*args: ty.Any, **kwargs: ty.Any) -> ty.Any:
            channel = signature.bind(*args, **kwargs).arguments[argument]
            with state.barrier(channel, exclusive=True):
                if state.blocked(channel):
                    raise ValueError("A restart is reserved for this lemon")

                return function(*args, **kwargs)

        return call

    return decorate


def scout(function: abc.Callable) -> abc.Callable:
    @functools.wraps(function)
    def call(session_id: str, *args: ty.Any, **kwargs: ty.Any) -> bool:
        with state.admission(channel_id("claude", session_id), replacement=True) as allowed:
            return function(session_id, *args, **kwargs) if allowed else False

    return call


def deliver(channel: str, output: abc.Callable[[str], None]) -> abc.Callable[[str], None]:
    def call(message: str) -> None:
        while state.blocked(channel):
            with db.connect() as conn:
                operation = state.active(conn, channel)
            if not operation or operation["token"] != os.environ.get("LEMONAID_RESTART_TOKEN"):
                raise ValueError("Restart holds delivery; changes remain pending")

            time.sleep(0.1)
        with state.admission(channel) as allowed:
            if not allowed:
                raise ValueError("Restart holds delivery; changes remain pending")

            output(message)

    return call


def turn_start(harness: str, stdin: str = "") -> bool:
    raw = stdin or sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return True

    if native.turn_allowed(data, harness):
        return True

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "A lemon restart is in progress; retry after it completes.",
            }
        )
    )
    return False


def submit(function: abc.Callable) -> abc.Callable:
    @functools.wraps(function)
    def call(stdin_data: str | None = None) -> None:
        raw = sys.stdin.read() if stdin_data is None else stdin_data
        if turn_start("claude", raw or "{}"):
            function(raw)

    return call


def notification(harness: str) -> abc.Callable:
    def decorate(function: abc.Callable) -> abc.Callable:
        signature = inspect.signature(function)

        @functools.wraps(function)
        def call(*args: ty.Any, **kwargs: ty.Any) -> ty.Any:
            bound = signature.bind_partial(*args, **kwargs)
            raw = bound.arguments.get("stdin_data")
            if raw is None:
                raw = sys.stdin.read()
            try:
                data = json.loads(raw or "{}")
            except ValueError:
                data = {}
            session = bound.arguments.get("session_id")
            if session:
                data["session_id"] = session
            session = data.get("session_id") or data.get("thread_id") or data.get("thread-id")
            target = native.channel(harness, session) if session else ""
            with state.barrier(target):
                if target and not native.observe(data, harness):
                    return None
                with db.connect() as conn:
                    known = native.registered(conn, target) if target else None
                if known and native.harness_parent(harness) is None:
                    return None

                bound.arguments["stdin_data"] = raw
                return function(*bound.args, **bound.kwargs)

        return call

    return decorate


def registration(function: abc.Callable) -> abc.Callable:
    @contextlib.contextmanager
    @functools.wraps(function)
    def call(
        kind: str, targets: abc.Iterable[str], channel: str, *args: ty.Any, **kwargs: ty.Any
    ) -> abc.Iterator:
        with contextlib.ExitStack() as stack:
            with state.admission(channel, replacement=True) as allowed:
                if not allowed:
                    raise ValueError("A restart holds watcher registration")

                waiter = stack.enter_context(function(kind, targets, channel, *args, **kwargs))
            yield waiter

    return call
