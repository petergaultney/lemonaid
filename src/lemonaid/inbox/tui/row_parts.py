"""The parts of a row every list draws alike: model label, directory, card context.

They share caches across lists and refreshes: the model each channel last
reported, and each row's project, whose name may take a hook run to learn.
"""

import dataclasses
from collections import abc

from rich.text import Text

from ...config import Config
from ...lemon_watchers import ModelInfo
from .. import db, undo
from . import brief_cards, card_context, inbox_rows, project_names


class RowParts:
    def __init__(
        self,
        config: Config,
        run_drain: abc.Callable[[abc.Coroutine], None],
        names_changed: abc.Callable[[], None],
    ) -> None:
        """`run_drain` runs project-name resolution off the UI thread; `names_changed`
        redraws once a name has arrived.
        """
        self._config = config
        self._run_drain = run_drain
        self._names_changed = names_changed
        self.models_by_channel: dict[str, ModelInfo] = {}
        # Each row's project, by (cwd, branch, area): finding one resolves paths,
        # which a refresh tick shouldn't repeat for rows that haven't changed.
        self.projects: dict[tuple[str, str, str], card_context.Part] = {}
        self.project_names = project_names.Cache()

    def _project_names_changed(self) -> None:
        self.projects.clear()
        self._names_changed()

    def project(self, n: db.Notification, area: str) -> card_context.Part:
        key = (n.metadata.get("cwd", ""), n.metadata.get("git_branch", ""), area)
        if key not in self.projects:
            if self.project_names.request(
                key[0], self._config.places.root_for(key[0]) if key[0] else None
            ):
                self._run_drain(self.project_names.drain(self._project_names_changed))
            self.projects[key] = card_context.project_part(
                self._config.places, *key, project_name=self.project_names.names.get(key[0], "")
            )

        return self.projects[key]

    def backend_value(self, n: db.Notification, is_unread: bool, *, history: bool = False) -> Text:
        return inbox_rows.backend_value(
            n, is_unread, self._config.tui, self.models_by_channel, history=history
        )

    def where_cell(self, n: db.Notification, is_unread: bool, area: str) -> Text:
        return inbox_rows.where_cell(n, is_unread, self._config.tui, lambda: self.project(n, area))

    def context_parts(
        self,
        n: db.Notification,
        is_unread: bool,
        area: str,
        card_brief: brief_cards.CardBrief | None = None,
        now: float = 0.0,
    ) -> list[card_context.Part]:
        return inbox_rows.context_parts(
            n, is_unread, self._config.tui, self.project(n, area), card_brief, now
        )


@dataclasses.dataclass(frozen=True)
class Lists:
    """What every list of sessions draws and edits with."""

    config: Config
    parts: RowParts
    brief_cache: brief_cards.BriefCache
    undo_stack: undo.Stack
