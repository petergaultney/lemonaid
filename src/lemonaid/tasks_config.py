"""The `[tasks]` table: whether new briefs get task dispositions."""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class TasksConfig:
    enabled: bool = False
    existing_task_templates: tuple[str, ...] = ("review",)  # must name an existing task


def parse(data: dict) -> TasksConfig:
    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        print("Warning: [tasks] enabled must be true or false", file=sys.stderr)
        enabled = False
    templates = data.get("existing_task_templates", list(TasksConfig.existing_task_templates))
    if not isinstance(templates, list) or not all(isinstance(t, str) for t in templates):
        print("Warning: [tasks] existing_task_templates must be a list of names", file=sys.stderr)
        templates = list(TasksConfig.existing_task_templates)
    return TasksConfig(enabled=enabled, existing_task_templates=tuple(templates))
