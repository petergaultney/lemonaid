"""A watch source with no lemonaid imports, for the tests. It follows `item:<name>`: the lines
of `$FAKE_SOURCE_DIR/<name>`, each one event. Creating `$FAKE_SOURCE_DIR/ready` makes it say
`ready` for every subscription it knows; `$FAKE_SOURCE_DIR/problem` makes polls report its text;
an `--end` argument ends the subscription. It writes each `forget` to `$FAKE_SOURCE_DIR/forgotten`.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

home = Path(os.environ["FAKE_SOURCE_DIR"])
known: set[str] = set()
out_lock = threading.Lock()
stdin, stdout = sys.stdin.buffer, sys.stdout.buffer


def send(data: bytes) -> None:
    with out_lock:
        stdout.write(data)
        stdout.flush()


def answer(lines: list[str]) -> None:
    body = "".join(f"{line}\n" for line in lines).encode()
    send(f"ok {len(body)}\n".encode() + body)


def notices() -> None:
    while True:
        time.sleep(0.05)
        if (home / "ready").exists():
            (home / "ready").unlink()
            for key in sorted(known):
                send(f"ready {key}\n".encode())


def poll(key: str, args: list[str], cursor: str) -> list[str]:
    known.add(key)
    name = args[0].removeprefix("item:")
    if (home / "problem").exists():
        return [f"problem {(home / 'problem').read_text().strip()}", "label fake problem"]

    seen = json.loads(cursor)["seen"] if cursor else 0
    items = (home / name).read_text().splitlines() if (home / name).exists() else []
    new = items[seen:]
    wake = ["wake", f"label {len(new)} new", f"count {len(new)}", *(f"text {i}" for i in new)]
    end = [f"end Stopped following {name}: it ended", "label stopped"] if "--end" in args else []
    return [*(wake if new else []), f"cursor {json.dumps({'seen': len(items)})}", *end, "every 600"]


send(b"lemonaid-source-plugin 1\n")
threading.Thread(target=notices, daemon=True).start()
while (header := stdin.readline()).endswith(b"\n"):
    fields = []
    while not (line := stdin.readline().decode()).startswith("text "):
        fields.append(line.rstrip("\n").partition(" ")[::2])
    text = stdin.read(int(line.split()[1])).decode()
    operation, _, key = header.decode().strip().partition(" ")
    args = [value for name, value in fields if name == "arg"]
    if operation == "check":
        if args and args[0].startswith("item:"):
            answer([f"target {args[0].removeprefix('item:')}"])
        else:
            send(f"error not an item: {' '.join(args)}\n".encode())
    elif operation == "poll":
        answer(poll(key, args, text))
    elif operation == "forget":
        known.discard(key)
        with (home / "forgotten").open("a") as f:
            f.write(f"{key}\n")
        answer([])
