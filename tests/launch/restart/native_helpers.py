"""Inspect only terminal devices owned by a native acceptance test."""

import json
import os
import termios
import time

import pytest

from lemonaid.launch.restart import pane


def terminal_flags(tty: str) -> list:
    descriptor = os.open(tty, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        return termios.tcgetattr(descriptor)[:6]
    finally:
        os.close(descriptor)


def claude_turn(home, sid, socket, target, marker, previous=0):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        files = list(home.glob(f"projects/*/{sid}.jsonl"))
        if len(files) == 1:
            records = [json.loads(line) for line in files[0].read_text().splitlines() if line]
            messages = [
                r.get("message", {})
                for r in records
                if r.get("type") == "assistant"
                and r.get("message", {}).get("model") != "<synthetic>"
            ]
            if sum(m.get("stop_reason") == "end_turn" for m in messages) > previous and any(
                marker in json.dumps(m.get("content", [])) and m.get("stop_reason") == "end_turn"
                for m in messages
            ):
                return records
        if pane.by_id(socket, target.pane).dead:
            break
        time.sleep(0.2)
    pytest.fail(
        "native Claude turn did not finish: "
        + pane.run(socket, "capture-pane", "-p", "-t", target.pane)
    )


def codex_turn(home, socket, target, previous=0):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if pane.by_id(socket, target.pane).dead:
            break
        files = list(home.glob("sessions/**/*.jsonl"))
        if len(files) == 1:
            records = [json.loads(line) for line in files[0].read_text().splitlines() if line]
            if sum(r.get("payload", {}).get("type") == "task_complete" for r in records) > previous:
                return records
        time.sleep(0.2)
    pytest.fail(
        "native turn did not finish: " + pane.run(socket, "capture-pane", "-p", "-t", target.pane)
    )
