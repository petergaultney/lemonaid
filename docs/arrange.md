# Arranging the inbox

`[inbox] arrange` names a program that decides the order of `lma`'s list and
what folds at its bottom. `lma` keeps it running, sends it a JSON snapshot of
the inbox whenever the rows change, and draws its answer. Everything else stays
`lma`'s: keys, the cursor, switching, briefs, and every action on a session.

```toml
[inbox]
arrange = "lemonaid inbox arrange serve ~/.config/lemonaid/arrange.py"
```

## Writing one in Python

`lemonaid inbox arrange serve FILE` runs `FILE`'s `arrange(snapshot)` function
in lemonaid's own interpreter, so it can import lemonaid. Start from the
inbox's own answer and change what you want:

```python
from lemonaid.inbox.arrange import answer

DAY = 24 * 3600


def arrange(snapshot):
    """The inbox's own order, with read `waiting` lemons idle for a day folded."""
    order = answer.default(snapshot)
    rows = {r["id"]: r for r in snapshot["rows"]}

    def idle(i):
        row, brief = rows[i], rows[i]["brief"]
        return (
            not row["unread"]
            and brief
            and brief["status"] == "waiting"
            and snapshot["now"] - brief["mtime"] > DAY
        )

    return {
        "rows": [i for i in order["rows"] if not idle(i)],
        "folded": [*order["folded"], *(i for i in order["rows"] if idle(i))],
        "fold_label": "quiet",
    }
```

`serve` loads the file again whenever it changes, so an edit takes effect at
the next snapshot without restarting `lma`. An exception in `arrange`, or in
loading the file, is answered as an error, and its traceback goes to stderr, so
`lma` shows the error and keeps its own order until the next snapshot.

## Trying one without `lma`

```sh
lemonaid inbox arrange check                    # the configured arranger
lemonaid inbox arrange check --command "..."    # another one
lemonaid inbox arrange snapshot --pretty        # what an arranger is sent
```

`check` sends the arranger one snapshot of the live inbox, prints the list as
`lma` would draw it, how long the answer took, the arranger's stderr, and every
problem: rows it left out, ids that aren't rows, unread rows it tried to fold,
fields `lma` doesn't know. It exits 1 if there were any.

## In `lma`

- **While the arranger has no usable answer, `lma` draws its own order.** The
  status line says why (`arrange: exited 1: KeyError: 'brief'`,
  `arrange: no answer in 2s`), and the arranger is restarted, waiting 1 s, then
  2 s, up to a minute between attempts.
- **The arranger's stderr goes to the lemonaid log** (`/tmp/lemonaid.log`, or
  `$LEMONAID_LOG`), under `lemonaid.arrange`. So do the problems `check`
  reports, once each.
- **The tick doesn't wait on it for long.** A snapshot goes out only when the
  rows change, and once a minute so an arranger can act on age. `lma` waits up
  to 50 ms for the answer and otherwise draws the newest answer it has.
- **The fold key works with an arranger** even without `[tui] fold_statuses`.
  The fold line is labeled with the answer's `fold_label`.
- **The lower table**, other terminals' sessions, keeps lemonaid's order.

## The protocol

Any program can be an arranger. It reads one JSON object per line on stdin and
writes one per line on stdout, in the same order, and keeps reading until stdin
closes. Flush after each answer.

### The snapshot

```json
{
  "version": 1,
  "layout": "sidebar",
  "width": 38,
  "now": 1790891360.3,
  "rows": [
    {
      "id": 1377,
      "channel": "claude:1a2b3c4d",
      "backend": "claude",
      "name": "lemonaid HQ",
      "emoji": "🍋",
      "unread": true,
      "pinned": false,
      "mid_turn": false,
      "message": "I started a design child...",
      "created_at": 1790891360.3,
      "read_at": null,
      "cwd": "/home/sam/src/lemonaid",
      "branch": "main",
      "tty": "/dev/ttys004",
      "brief": {
        "path": "/home/sam/.lemons/brief/2026-10-01-plan.md",
        "status": "blocked",
        "shown": "blocked",
        "needs_label": "Needs Sam",
        "needs": "Approve slice 1",
        "waiting_on": "",
        "running": "",
        "mtime": 1790891000.0,
        "since": 1790804600.0
      },
      "default": {"position": 0, "band": "blocked", "folded": false}
    }
  ]
}
```

- `layout` is `sidebar` (cards) or `table` (columns), and `width` the pane's width.
- `brief` is `null` for a session with no attached brief. Its `status` is the
  brief's own, which places the row, and `shown` is what the card is drawn as:
  `working` for a mid-turn lemon when `[tui] mid_turn_working` is on.
  `mtime` is the brief's last edit, and `since` when lemonaid first saw its
  current `status`.
- `default` is lemonaid's own answer: the row's position, its band (`pinned`,
  `alert`, `blocked`, `running`, `merge`, `review`, `unread done`, `done`,
  `unread`, `read`), and whether `fold_statuses` folds it.

### The answer

```json
{"rows": [1377, 1290, 1201], "folded": [1188], "fold_label": "quiet"}
```

- `rows` is the list in order, and `folded` the group folded at its bottom.
- Every field is optional. A row the answer leaves out goes where lemonaid's
  own order puts it.
- An unread row stays in the list even if the answer folds it, unless
  `[inbox] arrange_may_fold_unread = true`.
- `{"error": "..."}` reports a failure; `lma` shows it and draws its own order.
- Ids that aren't rows, and fields `lma` doesn't know, are ignored.
