"""Column, breakpoint and card-size constants for the inbox table."""

from ..utils import HERE_BAR

NAME_COLUMN = 3
BRANCH_COLUMN = 4
MESSAGE_COLUMN = 6
TTY_COLUMN = 7

# Terminal widths at which the weakest columns stop earning their space.
# Crossing a threshold takes some width back from Name to pay for the column it
# re-introduces; that trade is intended, and Name stays far above the fixed
# 14 chars it had before these breakpoints existed.
WIDE_LAYOUT_COLS = 132
MEDIUM_LAYOUT_COLS = 104

# Cards are for panes shaped tall and narrow. Two ways to qualify: too narrow for
# the columns to fit at all, or enough taller than wide that the rows are the
# abundant resource and the columns are the scarce one. The second case matters
# because a pane can be wide enough to draw every column and still only have room
# to show four characters of each - which is what a side pane usually is.
CARD_LAYOUT_COLS = 54

# A pane this narrow is a sidebar however short the window makes it. Above it,
# height decides - but only for panes narrow enough for the question to matter,
# so a sidebar does not change layout with the window it is joined to.
SIDEBAR_COLS = 72
CARD_ASPECT = 1.2  # rows per column, above which a pane counts as tall and narrow
CARD_HEIGHT = 3  # headline + one context line + one message line
CARD_MAX_HEIGHT = 14  # a card long enough to hold most messages whole
CARD_MAX_SHARE = 0.4  # most of a tall pane one card may claim
CARD_BODY_COLUMN = 0

# Ten cells hold the longest current model label (`Sonnet 4.6`); one more holds
# the pin in a single-line row. The fixed width prevents a row from reflowing
# when its model becomes known, and the labels share their right edge.
BACKEND_WIDTH = 11
CONTEXT_WIDTH = 7  # ` 999% ` and the model's padding, when readings are configured
CARD_MIN_TEXT = 16
CARD_CHROME_ROWS = 3  # title, status row, and a little slack
INDENT = " "  # one column, so a card's body clears the marker but little else
GROUP_RAIL = HERE_BAR  # one kind of edge, in the group's colour

# Cards draw their own gutter - a single space, with the marker in the column
# before it - so the table adds none. Every column a narrow pane spends on
# padding is one the message doesn't get.
CARD_CELL_PADDING = 0
COLUMN_CELL_PADDING = 1  # DataTable's own default, restored on the way back
TIME_CELL = 0
UNREAD_CELL = 1
BACKEND_CELL = 2
NAME_CELL = 3
BRANCH_CELL = 4
CWD_CELL = 5
MSG_CELL = 6
