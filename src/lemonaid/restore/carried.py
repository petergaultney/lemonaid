"""The launch flags a resumed lemon keeps: the model and effort it was started with.

A harness resumed from its session alone starts on its default model, so a lemon
started on a small model would come back on a larger one. lemonaid records each
harness's argv when it starts (`launch.restart.native`), and restore puts these
flags back on the resume line.
"""

from collections import abc
from pathlib import Path

# Flags that take a value, by harness. Codex's `-c key=value` carries only these keys.
_VALUED = {
    "claude": frozenset({"--model", "--effort"}),
    "codex": frozenset({"-m", "--model"}),
}
_CODEX_KEYS = frozenset({"model", "model_reasoning_effort"})


def _kept(harness: str, flag: str, value: str) -> bool:
    if harness == "codex" and flag in ("-c", "--config"):
        return value.partition("=")[0].strip() in _CODEX_KEYS

    return flag in _VALUED.get(harness, frozenset())


def _name(flag: str, value: str) -> str:
    """What a carried pair sets: its flag, or for `-c`, its key."""
    if flag in ("-c", "--config"):
        return value.partition("=")[0].strip()

    return "--model" if flag == "-m" else flag


def flags(harness: str, argv: abc.Sequence[str]) -> list[str]:
    """The flags in a harness's own *argv* that restore carries, as `--flag value` pairs."""
    carried: list[str] = []
    for i, arg in enumerate(argv[1:], start=1):
        flag, joined, value = arg.partition("=")
        if joined and flag.startswith("--") and _kept(harness, flag, value):
            carried += [flag, value]
        elif i + 1 < len(argv) and _kept(harness, arg, argv[i + 1]):
            carried += [arg, argv[i + 1]]
    return carried


def _harness_at(argv: abc.Sequence[str], harness: str) -> int | None:
    """Where the harness's own name is in a resume line, as `claude` in `lemonaid claude ...`."""
    return next((i for i, arg in enumerate(argv) if Path(arg).name == harness), None)


def apply(harness: str, argv: abc.Sequence[str], carried: abc.Sequence[str]) -> list[str]:
    """*argv*, a resume line, with *carried* flags it doesn't already set.

    `lemonaid claude resume ID [PROMPT]` takes no flags, so it becomes the equivalent
    `lemonaid claude FLAGS --resume ID [PROMPT]`.
    """
    found = flags(harness, argv)
    present = {_name(f, v) for f, v in zip(found[::2], found[1::2], strict=True)}
    missing = [
        part
        for flag, value in zip(carried[::2], carried[1::2], strict=True)
        if _name(flag, value) not in present
        for part in (flag, value)
    ]
    at = _harness_at(argv, harness)
    if not missing or at is None:
        return list(argv)

    head, rest = list(argv[: at + 1]), list(argv[at + 1 :])
    if harness == "claude" and rest[:1] == ["resume"] and len(rest) >= 2:
        return [*head, *missing, "--resume", *rest[1:]]

    return [*head, *missing, *rest]
