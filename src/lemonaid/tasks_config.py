"""The `[tasks]` table: whether new briefs get task dispositions, and how the inspector runs."""

import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TasksConfig:
    enabled: bool = False
    existing_task_templates: tuple[str, ...] = ("review",)  # must name an existing task
    checker: tuple[str, ...] = ()  # argv; empty runs the default checker
    checker_timeout: float = 30.0
    inspect_interval: float = 0.0  # seconds between the scout host's passes; 0 runs none
    challenge_interval: float = (
        300.0  # seconds before replacing an unreceived challenge; 0 sends none
    )
    opt_out: dict[str, str] = field(default_factory=dict)  # Lemon-ID -> why it gets no challenges
    policy: dict[str, str] = field(default_factory=dict)  # passed to the checker as policy.*


def _strings(data: dict, name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = data.get(name, list(default))
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        print(f"Warning: [tasks] {name} must be a list of strings", file=sys.stderr)
        return default

    return tuple(value)


def _flag(data: dict, name: str, default: bool) -> bool:
    value = data.get(name, default)
    if not isinstance(value, bool):
        print(f"Warning: [tasks] {name} must be true or false", file=sys.stderr)
        return default

    return value


def _seconds(data: dict, name: str, default: float, allow_zero: bool) -> float:
    value = data.get(name, default)
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or value < 0
        or (value == 0 and not allow_zero)
    ):
        need = "a non-negative" if allow_zero else "a positive"
        print(f"Warning: [tasks] {name} must be {need} number", file=sys.stderr)
        return default

    return float(value)


def _reasons(data: dict) -> dict[str, str]:
    value = data.get("opt_out", {})
    if not isinstance(value, dict) or not all(
        isinstance(v, str) and v.strip() for v in value.values()
    ):
        print("Warning: [tasks.opt_out] maps each Lemon-ID to its reason", file=sys.stderr)
        return {}

    return {str(k): v.strip() for k, v in value.items()}


def parse(data: dict) -> TasksConfig:
    policy = data.get("policy", {})
    if not isinstance(policy, dict) or not all(
        isinstance(v, str | int | float) and not isinstance(v, bool) for v in policy.values()
    ):
        print("Warning: [tasks.policy] values must be strings or numbers", file=sys.stderr)
        policy = {}
    return TasksConfig(
        enabled=_flag(data, "enabled", False),
        existing_task_templates=_strings(
            data, "existing_task_templates", TasksConfig.existing_task_templates
        ),
        checker=_strings(data, "checker", ()),
        checker_timeout=_seconds(
            data, "checker_timeout", TasksConfig.checker_timeout, allow_zero=False
        ),
        inspect_interval=_seconds(
            data, "inspect_interval", TasksConfig.inspect_interval, allow_zero=True
        ),
        challenge_interval=_seconds(
            data, "challenge_interval", TasksConfig.challenge_interval, allow_zero=True
        ),
        opt_out=_reasons(data),
        policy={str(k): str(v) for k, v in policy.items()},
    )
