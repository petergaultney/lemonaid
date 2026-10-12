"""The cells of one inbox row, for the main and other-sources tables."""

import typing as ty
from collections import abc

from rich.text import Text

from ...config import TuiConfig
from ...lemon_watchers import ModelInfo, fish_path
from .. import context_use, db
from . import backend_indicators, brief_cards, card_context, pr_numbers, row_cells, utils
from .utils import backend_cell, jump_gutter, styled_cell


def _context_percent(
    n: db.Notification, model: ModelInfo | None, context_threshold: ty.Any
) -> int | None:
    used = n.metadata.get("context_tokens")
    window = n.metadata.get("context_window")
    if not isinstance(used, int):
        return None

    threshold = context_use.threshold_for(
        context_threshold,
        n.channel.split(":")[0],
        model.model if model else "",
    )
    if threshold is None:
        return None

    return context_use.percent(used, window if isinstance(window, int) else 0, threshold)


def backend_value(
    n: db.Notification,
    is_unread: bool,
    tui: TuiConfig,
    models_by_channel: dict[str, ModelInfo],
    *,
    history: bool = False,
) -> Text:
    """The model label; records `n`'s model in `models_by_channel` when it carries one."""
    remembered = models_by_channel.get(n.channel)
    model = n.metadata.get("model")
    if isinstance(model, str) and model:
        provider = n.metadata.get("model_provider")
        if not isinstance(provider, str):
            provider = remembered.provider if remembered else ""
        remembered = ModelInfo(provider, model)
        models_by_channel[n.channel] = remembered

    return backend_indicators.backend_text(
        n.channel,
        tui.backend_labels,
        is_unread,
        model=remembered.model if remembered else "",
        model_provider=remembered.provider if remembered else "",
        history=history,
        context_percent=None if history else _context_percent(n, remembered, tui.context_threshold),
    )


def where_cell(
    n: db.Notification,
    is_unread: bool,
    tui: TuiConfig,
    project: abc.Callable[[], card_context.Part],
) -> Text:
    """The directory column: the project, unless `card_fields` asks for the cwd instead."""
    if "project" not in tui.card_fields:
        return styled_cell(fish_path(n.metadata.get("cwd", "")), is_unread, "cwd")

    where = project()
    if tui.project_name_colors and where.field == "project" and where.project_name:
        return utils.styled_project_cell(where.text.plain, where.project_name, is_unread)
    return styled_cell(where.text.plain, is_unread, where.field)


def context_parts(
    n: db.Notification,
    is_unread: bool,
    tui: TuiConfig,
    project: card_context.Part,
    card_brief: brief_cards.CardBrief | None = None,
    now: float = 0.0,
) -> list[card_context.Part]:
    return card_context.parts(
        tui.card_fields,
        row_cells.time_cell(n.created_at, is_unread, neutral_timing=tui.project_name_colors),
        project,
        n.metadata.get("git_branch", ""),
        n.metadata.get("cwd", ""),
        is_unread,
        card_brief.age_text(now) if card_brief else "",
        tui.project_name_colors,
        neutral_timing=tui.project_name_colors,
    )


def active_row(
    n: db.Notification,
    row_index: int,
    is_here: bool,
    is_pinned: bool,
    emojis: abc.Mapping[str, str],
    backend: Text,
    where: Text,
    detached: Text,
    tui: TuiConfig,
    wordybin: str = "",
    pr_number: pr_numbers.PR | None = None,
) -> tuple[str, list[Text]]:
    """The main-table row for a session, keyed by notification id.

    `row_index` is the session's position in the list, which is what its jump
    digit names - so a row's number changes when the list reorders.
    """
    is_unread = n.is_unread
    return str(n.id), [
        row_cells.time_cell(n.created_at, is_unread, neutral_timing=tui.project_name_colors),
        Text("●", style=utils.unread_marker_style()) if is_unread else Text(""),
        backend_cell(backend, is_pinned),
        jump_gutter(row_index, is_here)
        + row_cells.name_cell(n, emojis, wordybin, is_unread, pr_number)
        + detached,
        styled_cell(n.metadata.get("git_branch", ""), is_unread, "branch"),
        where,
        styled_cell(n.message, is_unread, "message"),
        styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), is_unread, "tty"),
    ]


def other_row(
    n: db.Notification,
    emojis: abc.Mapping[str, str],
    backend: Text,
    where: Text,
    tui: TuiConfig,
    wordybin: str = "",
    pr_number: pr_numbers.PR | None = None,
) -> tuple[str, list[Text]]:
    """The non-switchable-table row for a session. Always dimmed."""
    return str(n.id), [
        row_cells.time_cell(n.created_at, False, neutral_timing=tui.project_name_colors),
        Text("○", style="dim") if n.is_unread else Text(""),
        backend,
        row_cells.name_cell(n, emojis, wordybin, False, pr_number),
        styled_cell(n.metadata.get("git_branch", ""), False, "branch"),
        where,
        styled_cell(n.message, False, "message"),
        styled_cell(n.metadata.get("tty", "").replace("/dev/", ""), False, "tty"),
    ]
