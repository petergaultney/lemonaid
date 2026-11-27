"""A document plugin with no lemonaid imports, for the tests: a comment is a whole line
`%% <author>: <text>`. Flags change it: --fail exits before saying hello, --crash exits
on its first request, --incomplete reports that some threads were not read, --note TEXT
adds a note, --notice sends a notice line after hello and before each answer, --hang
never answers, --deaf never reads a request, and --echo-env NAME answers every request with that variable's value.
"""

import hashlib
import os
import sys
import time

flags = sys.argv[1:]
note = flags[flags.index("--note") + 1] if "--note" in flags else ""
if "--fail" in flags:
    print("fake plugin failed on purpose", file=sys.stderr)
    sys.exit(3)


def threads(text: str, names: set[str]) -> str:
    lines = []
    for line in text.split("\n"):
        if not line.startswith("%% "):
            continue

        rest = line[3:]
        author = rest.partition(":")[0]
        lines += [f"thread fake-{hashlib.sha1(rest.encode()).hexdigest()[:12]}", f"last {author}"]
        lines += [] if author in names else ["waiting"]
        lines.append(f"text {rest}")
    lines += [f"note {note}"] if note else []
    lines += ["incomplete"] if "--incomplete" in flags else []
    return "".join(f"{line}\n" for line in lines)


def body(text: str) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if not line.startswith("%% "))


stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
if "--deaf" in flags:
    stdout.write(b"lemonaid-doc-plugin 1\n")
    stdout.flush()
    time.sleep(60)
stdout.write(b"lemonaid-doc-plugin 1\n" + (b"ready hello\n" if "--notice" in flags else b""))
stdout.flush()
while first := stdin.readline():
    if "--crash" in flags:
        sys.exit(4)

    operation = first.decode().split(" ", 1)[0]
    names = set()
    while (line := stdin.readline().decode()).startswith("name "):
        names.add(line[5:].rstrip("\n"))
    text = stdin.read(int(line.split()[1])).decode()
    if "--hang" in flags:
        continue

    result = (body(text) if operation == "body" else threads(text, names)).encode()
    if "--echo-env" in flags:
        result = os.environ.get(flags[flags.index("--echo-env") + 1], "").encode()
    if "--notice" in flags:
        stdout.write(f"ready {operation}\n".encode())
    stdout.write(f"ok {len(result)}\n".encode() + result)
    stdout.flush()
