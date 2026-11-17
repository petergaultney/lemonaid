"""Whether a tree stands on its lemon list, the way a grown block is meant to look: the trunk's
foot on the list's top edge, over its span.
"""

from ..draw import tag_fit

Rect = tuple[int, int, int, int]


def off(fitted: tag_fit.Fitted, list_rect: Rect) -> str:
    """Why a tree whose tag was *fitted* doesn't stand on its list at *list_rect*, or "" when it
    does: the list hangs from the tag, directly under the trunk, and the trunk is over its span.
    """
    x, y, w, _ = list_rect
    trunk_x = fitted.trunk[0]
    first, last = x + 1, x + w - 2  # the columns of the top edge inside its corners

    def cols(n: int) -> str:
        return f"{n} column{'' if n == 1 else 's'}"

    def rows(n: int) -> str:
        return f"{n} row{'' if n == 1 else 's'}"

    reasons = []
    if trunk_x < first:
        reasons.append(f"the trunk is {cols(first - trunk_x)} left of the list's left end")
    elif trunk_x > last:
        reasons.append(f"the trunk is {cols(trunk_x - last)} past the list's right end")
    if y > fitted.y:
        reasons.append(f"the list starts {rows(y - fitted.y)} below the trunk's foot")
    elif y < fitted.y:
        reasons.append(f"the list starts {rows(fitted.y - y)} above the trunk's foot")
    if len(reasons) == 2 and y <= fitted.y:
        return f"the list is beside the tree ({'; '.join(reasons)})"

    return "; ".join(reasons)
