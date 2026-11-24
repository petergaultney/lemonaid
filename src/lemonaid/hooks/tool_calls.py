"""What a tool call does, read from a hook's input in either harness: its shell commands,
and the files it writes."""

import json
import os
import re
import typing as ty
from collections import abc
from pathlib import Path

_EXEC_CALL = re.compile(r"exec_command\s*\(")
# The call's `cmd` property, its key quoted or bare, its value any JavaScript string literal.
_CMD_PROPERTY = re.compile(
    r"""(?:["']cmd["']|\bcmd)\s*:\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)""",
    re.DOTALL,
)
_PATCH = "*** Begin Patch"
# A wrapped `exec` script's `tools.apply_patch(...)`, its argument any JavaScript string literal.
_APPLY_PATCH = re.compile(
    r"""apply_patch\s*\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)""",
    re.DOTALL,
)
_PATCH_FILE = re.compile(r"^\*\*\* (Add File|Update File|Move to): (.+?)\s*$", re.MULTILINE)
_FILE_TOOLS = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}


def strings(value: ty.Any) -> abc.Iterator[str]:
    """Every string anywhere in a tool's input or response, whose shape varies by tool and harness."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def _unquoted(literal: str) -> str:
    """A JavaScript string literal's text, near enough to read shell words from."""
    if literal[0] == '"':
        try:
            return json.loads(literal)
        except json.JSONDecodeError:
            pass
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m[1], m[1]), literal[1:-1])


def commands(tool_input: ty.Any) -> abc.Iterator[str]:
    """The shell commands a tool call runs: Claude's `command`, Codex's `cmd`, and the
    `cmd` of each `tools.exec_command({...})` inside Codex's wrapped `exec` script. A
    Codex patch, which also arrives as `command` or inside the script, is not one."""
    script = tool_input
    if isinstance(tool_input, dict):
        for key in ("command", "cmd"):
            yield from (s for s in strings(tool_input.get(key)) if _PATCH not in s)
        script = tool_input.get("input")
    for text in strings(script):
        text = _APPLY_PATCH.sub("", text)  # a patch's text names no command
        for call in _EXEC_CALL.finditer(text):
            if found := _CMD_PROPERTY.search(text, call.end()):
                yield _unquoted(found.group(1))


def _patches(tool_input: ty.Any) -> abc.Iterator[str]:
    """The patches a call applies: a patch tool's own text, or each `tools.apply_patch`
    argument in a wrapped `exec` script."""
    for text in strings(tool_input):
        wrapped = [] if text.lstrip().startswith(_PATCH) else _APPLY_PATCH.findall(text)
        if wrapped:
            yield from map(_unquoted, wrapped)
        elif _PATCH in text:
            yield text


def _patch_files(tool_input: ty.Any, cwd: Path) -> abc.Iterator[tuple[str, Path]]:
    for patch in _patches(tool_input):
        for match in _PATCH_FILE.finditer(patch):
            yield match.group(1), cwd / Path(match.group(2)).expanduser()


def _cwd(data: dict) -> Path:
    return Path(data.get("cwd") or os.getcwd())


def _file_tool_path(data: dict) -> Path | None:
    key, tool_input = _FILE_TOOLS.get(str(data.get("tool_name"))), data.get("tool_input")
    raw = tool_input.get(key) if key and isinstance(tool_input, dict) else None
    return _cwd(data) / Path(raw).expanduser() if isinstance(raw, str) and raw else None


def written(data: dict) -> list[Path]:
    """The files the call writes: a Claude file tool's path, or the files a Codex patch
    adds, updates or moves to."""
    if path := _file_tool_path(data):
        return [path]

    return list(dict.fromkeys(path for _, path in _patch_files(data.get("tool_input"), _cwd(data))))


def created(data: dict) -> list[Path]:
    """The files the call creates: those a Codex patch adds or moves to, or, once a Claude
    `Write` has run, its path when its result says it created the file."""
    if path := _file_tool_path(data):
        response = data.get("tool_response")
        return [path] if isinstance(response, dict) and response.get("type") == "create" else []

    return list(
        dict.fromkeys(
            path
            for kind, path in _patch_files(data.get("tool_input"), _cwd(data))
            if kind != "Update File"
        )
    )
