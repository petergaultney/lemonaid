"""Archive the saved answer selected in the brief view."""

from ....brief import answer_edit
from . import brief_items


def archive(item: brief_items.Item, all_answers: bool) -> str:
    path = item.choice[0]
    moved = answer_edit.archive(path, None if all_answers else 1, "" if all_answers else item.body)
    return f"Archived {moved} saved answer{'s' if moved != 1 else ''} from {path.stem}"
