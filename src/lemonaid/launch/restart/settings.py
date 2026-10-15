"""Explicit native settings and conservative configured-command planning."""

import json
import os
import shlex
import shutil
import typing as ty
from collections import abc
from pathlib import Path

from ...claude import launch_args
from ...config import Config
from ...inbox import db
from ...resume import build_resume_command
from . import arguments
from . import environment as launch_env


def _value(argv: list[str], *flags: str) -> str:
    values = [
        arg.split("=", 1)[1] if "=" in arg else argv[i + 1] if i + 1 < len(argv) else ""
        for i, arg in enumerate(argv)
        if arg.split("=", 1)[0] in flags
    ]
    if len(set(values)) > 1:
        raise ValueError(f"Conflicting {flags[0]} flags")

    return values[0] if values else ""


def capture(
    harness: str, pid: int, data: dict[str, ty.Any], environment: abc.Mapping[str, str]
) -> dict[str, ty.Any]:
    argv = launch_args.argv(pid)
    if not argv:
        raise ValueError("Cannot recover the harness's exact launch arguments")

    model = data.get("model") or _value(argv, "--model", "-m")
    if isinstance(model, dict):
        model = model.get("id")
    if not isinstance(model, str) or not model:
        raise ValueError("Native effective model is unavailable; refusing to choose a default")

    if model in ("opus", "sonnet", "haiku", "default", "best"):
        raise ValueError(
            "A model alias cannot freeze the effective model; a native model observation is required"
        )

    launch_environment = launch_env.capture(harness, environment)

    if harness == "claude":
        permission = data.get("permission_mode") or _value(argv, "--permission-mode")
        if not permission and "--dangerously-skip-permissions" in argv:
            permission = "bypassPermissions"
        if not permission:
            raise ValueError("Native effective Claude permission mode is unavailable")

        return {
            "model": model,
            "permission": permission,
            "argv": argv,
            "environment": launch_environment,
            "native_homes": launch_env.homes(launch_environment),
        }

    if "--no-daemon" not in argv or any(w in argv for w in ("--remote", "app-server")):
        raise ValueError("Codex restart requires a dedicated --no-daemon TUI")

    sandbox = data.get("sandbox_policy") or _value(argv, "--sandbox", "-s")
    if isinstance(sandbox, dict):
        sandbox = sandbox.get("type")
    if isinstance(sandbox, str):
        sandbox = sandbox.replace("_", "-")
    approval = data.get("approval_policy") or _value(argv, "--ask-for-approval", "-a")
    if not sandbox and not approval and "--dangerously-bypass-approvals-and-sandbox" in argv:
        sandbox, approval = "danger-full-access", "never"
    if sandbox not in ("read-only", "workspace-write", "danger-full-access") or approval not in (
        "never",
        "on-request",
    ):
        raise ValueError("Native effective Codex sandbox and approval settings are unavailable")

    effort = (
        data.get("effort") or data.get("reasoning_effort") or data.get("model_reasoning_effort")
    )
    provider = data.get("model_provider")
    if not effort or not provider:
        raise ValueError("Native effective Codex reasoning effort and provider are unavailable")

    return {
        "model": model,
        "sandbox": sandbox,
        "approval": approval,
        "profile": _value(argv, "--profile", "-p"),
        "effort": effort,
        "provider": provider,
        "argv": argv,
        "environment": launch_environment,
        "native_homes": launch_env.homes(launch_environment),
    }


def command(row: db.Notification, config: Config, settings: dict[str, ty.Any]) -> list[str]:
    harness = row.channel.partition(":")[0]
    resumable = build_resume_command(config, row.channel, row.metadata)
    if resumable is None or resumable[0] != row.metadata["cwd"]:
        raise ValueError("The configured resume command cannot preserve this directory")

    words = resumable[1]
    if any(set(token) <= set("();<>|&") for token in words):
        raise ValueError("Compound resume commands are unsupported")

    if words[:3] == ["lemonaid", "claude", "resume"]:
        # The wrapper changes cwd and accepts no model/permission arguments.
        if len(words) != 4:
            raise ValueError("Unsupported Claude resume wrapper arguments")
        words = ["claude", "--resume", words[3]]
    if Path(words[0]).name != harness:
        raise ValueError("Cannot verify settings through this configured resume wrapper")
    search_path = settings.get("environment", {}).get("PATH")
    executable = shutil.which(harness, path=os.defpath if search_path is None else search_path)
    if not executable:
        raise ValueError(f"{harness} is unavailable on the launch PATH")

    session = str(row.metadata["session_id"])
    if session not in words or any(
        w in words
        for w in ("--last", "--continue", "--fork-session", "fork", "--remote", "--worktree")
    ):
        raise ValueError("Resume must name the exact native session without forking")

    configured_model = _value(words, "--model", "-m")
    if configured_model and configured_model != settings["model"]:
        raise ValueError("Configured resume model conflicts with the native model")

    if harness == "claude":
        if "--resume" not in words:
            raise ValueError("Claude resume command needs --resume SESSION_ID")
        flags = ["--model", settings["model"], "--permission-mode", settings["permission"]]
    else:
        if len(words) < 2 or words[1] != "resume":
            raise ValueError("Codex resume command must begin with codex resume")
        flags = [
            "--no-daemon",
            "--model",
            settings["model"],
            "--sandbox",
            settings["sandbox"],
            "--ask-for-approval",
            settings["approval"],
        ]
        if settings.get("profile"):
            flags += ["--profile", settings["profile"]]
        for field, key in (("effort", "model_reasoning_effort"), ("provider", "model_provider")):
            if settings.get(field):
                flags += ["-c", f"{key}={json.dumps(settings[field])}"]
        flags += ["-c", "check_for_update_on_startup=false"]
    # Native global options belong before Claude's resume flag and after Codex's subcommand.
    retained = arguments.preserve(settings["argv"], words, settings)
    return [
        executable,
        *([] if harness == "claude" else ["resume"]),
        *retained,
        *flags,
        *(["--resume", session] if harness == "claude" else [session]),
    ]


def line(argv: list[str], prompt: str, environment: dict[str, str | None] | None = None) -> str:
    # A tmux shell can rebuild PATH in its startup files, after tmux applies -e.
    prefix = launch_env.prefix(environment) if environment else []
    return "exec " + shlex.join([*prefix, *argv, prompt])
