# Inbox rows for a lemon

A tool can keep a row in the inbox for a lemon without being a session itself: a document plugin's "this lemon replied in your file" row, say. The row is an ordinary notification, written with `lemonaid inbox add`; two metadata keys make it belong to a lemon.

```sh
lemonaid inbox add "my-tool:claude:abc|/notes/plan.md" "2 replies" -n "↳ plan.md · 2 unread" \
  --under claude:abc --hide-when-read \
  --metadata '{"opener": "editor", "path": "/notes/plan.md", "open_uri": "file:///notes/plan.md"}'
lemonaid inbox read --channel "my-tool:claude:abc|/notes/plan.md"
```

- **`under`** (`--under`): the lemon's channel. The row is drawn right under that lemon, in its groups, wherever the lemon is drawn; an unread row brings a folded or hidden lemon back with it. A lemon in another terminal's pane takes its rows there. A row whose lemon has no terminal, or that names none (`--under ""`), is drawn on its own in every terminal while unread. The row has no model label of its own.
- **`hide_when_read`** (`--hide-when-read`): the row leaves the inbox once read. History keeps it.
- The channel is yours to choose: `inbox add` updates the row with the same channel, so one channel per thing you track (per file and lemon above) keeps one row each. `inbox read --channel` marks it read.
- `name` is the row's label; write it again on each update to keep a count in it current.

A lemon finds its own channel with `lemonaid brief id --self --json` (`channel`), and the name its own document waiter counts as its signature with `lemonaid watch doc --signature <doc>`.

## Opening the row

Enter on a row runs, in order:

1. The `[inbox.openers]` command the row's `opener` names, with `{path}` filled from the row's `path`. The command comes from your config; the row supplies only the path, and no shell runs it.
2. The row's `open_uri`, handed to `open`.
3. Otherwise, the session's own terminal, as for any lemon.

```toml
[inbox.openers]
editor = "my-editor open {path} --focus"
```

Rows in another terminal's pane are opened from here too, since they name a file on this machine rather than a session.
