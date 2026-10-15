"""Recover operating arguments without replaying conversation or terminal actions."""

import typing as ty

_VALUES = {
    "--model",
    "-m",
    "--permission-mode",
    "--settings",
    "--setting-sources",
    "--profile",
    "-p",
    "--sandbox",
    "-s",
    "--ask-for-approval",
    "-a",
    "--config",
    "-c",
    "--effort",
    "--agent",
    "--agents",
    "--mcp-config",
    "--system-prompt",
    "--append-system-prompt",
    "--allowedTools",
    "--allowed-tools",
    "--disallowedTools",
    "--disallowed-tools",
    "--tools",
    "--add-dir",
    "--plugin-dir",
    "--enable",
    "--disable",
}
_SWITCHES = {
    "--no-daemon",
    "--no-alt-screen",
    "--search",
    "--approve-for-me",
    "--dangerously-bypass-approvals-and-sandbox",
    "--dangerously-bypass-hook-trust",
    "--dangerously-skip-permissions",
    "--allow-dangerously-skip-permissions",
    "--strict-config",
    "--chrome",
    "--no-chrome",
    "--verbose",
    "--remote-control",
}
_IDENTITY = {"--resume", "-r", "--session-id", "--name", "-n", "--cd", "-C"}
_ALIASES = {
    "-m": "--model",
    "-p": "--profile",
    "-s": "--sandbox",
    "-a": "--ask-for-approval",
    "-c": "--config",
}
_MULTIPLE = {
    "--add-dir",
    "--allowedTools",
    "--allowed-tools",
    "--disallowedTools",
    "--disallowed-tools",
    "--tools",
    "--mcp-config",
    "--plugin-dir",
}


def operating(argv: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    index = 1
    while index < len(argv):
        argument = argv[index]
        flag, equals, value = argument.partition("=")
        if flag in _VALUES | _IDENTITY:
            if not equals:
                index += 1
                if index >= len(argv):
                    raise ValueError(f"Missing value for {flag}")
                value = argv[index]
            if flag in _VALUES:
                result.append((_ALIASES.get(flag, flag), value))
            if flag in _MULTIPLE and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
                raise ValueError(f"Cannot unambiguously preserve multiple values for {flag}")
        elif flag in _SWITCHES:
            result.append((flag, ""))
        elif flag.startswith("-"):
            raise ValueError(f"Cannot preserve unsupported operating flag {flag}")
        index += 1
    return result


def preserve(source: list[str], configured: list[str], effective: dict[str, ty.Any]) -> list[str]:
    original = operating(source)
    requested = operating(configured)
    for flag, value in requested:
        if (flag, value) not in original and flag not in {"--model", "--no-daemon"}:
            raise ValueError(
                f"Configured {flag} differs from the running session's operating settings"
            )

    # Model and permission selectors are supplied from fresh native settings separately.
    selectors = {
        "--no-daemon",
        "--model",
        "--permission-mode",
        "--sandbox",
        "--ask-for-approval",
        "--profile",
        "--dangerously-skip-permissions",
        "--dangerously-bypass-approvals-and-sandbox",
    }
    if effective.get("permission") == "bypassPermissions":
        selectors.discard("--dangerously-skip-permissions")
    return [
        part
        for flag, value in original
        if flag not in selectors
        for part in ([flag, value] if value else [flag])
    ]
