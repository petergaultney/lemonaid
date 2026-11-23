# Review comments in a file

lemonaid keeps review comments in the file they are about: small anchor markers in the
body mark the text a thread is about, and every comment is one JSON line in a section at
the end of the file that we only ever append to. Editors render the threads beside the
text; the raw file is not meant to be read as a conversation.

Python and Markdown files are supported.

## Anchors

An anchor's id is the id of the thread's first comment.

| Marker | Where | What removing it removes |
|---|---|---|
| `# [lma:SleepRib]`, `# [/lma:SleepRib]` | Python, alone on a line | its line and the line ending after it |
| `<!-- [lma:SleepRib] -->`, `<!-- [/lma:SleepRib] -->` | Markdown, inline | only itself |
| `<wbr><!-- [lma:SleepRib] wbr -->` | Markdown, inline, where a comment starts a line's text (see below) | only itself, its own `<wbr>` included |
| `<!-- [lma:SleepRib]: -->`, `<!-- [/lma:SleepRib]: -->` | Markdown, alone on a line | its line and the line ending after it |

A marker with no closing marker is a point anchor.

```python
def f():
    # [lma:SleepRib]
    results = executor.map(work, items)
    # [/lma:SleepRib]
    return results
```

- A marker's *carrier* is what removing it removes, and its spelling alone decides it, as
  the table says, so editing the text around a marker never changes it. A marker spelled
  for its own line that has other text beside it carries only itself; one on the body's
  last line, which has no line ending, carries just the line. The anchored text runs from
  the end of the opening carrier to the start of the closing one.
- In Markdown, a comment doesn't change how the document renders. CommonMark reads a
  line whose text starts with `<!--` as an HTML block rather than Markdown, even a
  list item's or a block quote's text, or a line in the middle of a paragraph, which
  it then ends. So lemonaid writes an opening marker after the line's block syntax,
  next to the text: after a heading's `#`s and inside a table row's first cell as is,
  and after a list item's or block quote's markers, or at a paragraph line's start,
  with an empty `<wbr>` in front, spelled `<wbr><!-- [lma:X] wbr -->`. `<wbr>` is a
  workaround: an HTML word-break opportunity, which renders nothing, so the line no
  longer starts with `<!--`; it belongs to the marker, which says so with ` wbr`, and
  goes when the marker does; a `<wbr>` anyone else wrote is left alone. A closing
  marker goes before a heading's closing `#`s, a trailing backslash or a table row's
  last `|`. A comment is refused where no marker can be invisible: in YAML
  frontmatter, on a table's delimiter row or an empty heading, or starting on a
  thematic break or a setext underline (one that ends on either gets its closing
  marker on a line of its own after it). Whatever the rules place, lemonaid renders
  the document with and without the markers (CommonMark with tables, through markdown-
  it-py) and refuses the comment if the HTML differs, as on a link reference
  definition.
- lemonaid writes inline Markdown markers around the selected text, trimmed of
  whitespace at its ends. It writes the own-line spelling around a fenced block,
  indented like the fence so a fence inside a list item stays inside it, and on a line
  that holds only markers, where an inline marker would change what the others remove.
  It never writes inside an existing marker or between a CR and its LF.
- A Python point anchor covers the line below it. A Markdown point anchor is a position.
- Ranges may nest or overlap.
- Markers inside Python strings and Markdown code (code spans, fenced blocks at any
  block-quote depth, and indented code blocks outside lists and quotes) are text, not
  markers. A Python marker is a whole line in the file as written, so a comment after a
  string's closing quotes is code. A selection that starts or ends inside code grows to
  cover it. Around a fenced block, each marker takes a line of its own, so the fence
  still starts its line, and a point at or inside a fence goes on its own line before
  it. A closing fence may be longer than the opening one.
- A Python marker never goes inside a string that spans lines or after a backslash
  continuation: the range grows a line at a time until it is outside both. It can't go
  above a shebang or an encoding line, which Python reads by position.
- A Python file with a string that is never closed, which is common while typing, can't
  be commented on or stripped until the string is closed. Its threads are still read,
  and the open string is reported as an error.
- Inserted markers and records use the file's line ending. lemonaid doesn't write to a
  file that ends lines with a bare CR.
- Before it returns an edit, lemonaid parses the result and refuses the edit unless it
  reads back exactly what it added: the new comment once, its anchor, every marker and
  anchor that was there before, and no new errors. It also refuses an id the file
  already uses.
- An id matches `[A-Za-z][\w-]*` and is unique in the file. lemonaid makes ids with
  WordyBin. `threads` is reserved.

## The threads section

```python
# [lma:threads]
# {"id": "SleepRib", "author": "Sam Lee", "at": "2026-11-19T19:40:00Z", "body": "why not `yield_results`?"}
# {"id": "TinOwl", "re": "SleepRib", "span": [8, 22], "author": "BraveFig (Author)", "at": "2026-11-19T19:41:12Z", "body": "it fails fast"}
# {"resolves": "TinOwl", "author": "Sam Lee", "at": "2026-11-19T19:50:30Z"}
```

```markdown
<!-- [lma:threads]
{"id": "SleepRib", "author": "Sam Lee", "at": "2026-11-19T19:40:00Z", "body": "..."}
-->
```

The header is a whole line at column 0, exactly as shown, so an indented or quoted example
is text. In Python the section starts at the header and runs to the end of the file; in
Markdown it is one HTML comment at the end of the file. The one line ending before the
header belongs to the section, since lemonaid always writes one there. In Markdown we
write `>` as
`\u003e` inside it so a body can't close the comment.

| Record | Fields |
|---|---|
| Comment | `id`, `author`, `at` (ISO 8601, with a UTC offset of zero), `body` (Markdown), and `"by": "lemon"` on a comment `lemonaid comments` wrote; a comment without it is a person's |
| Reply | a comment with `re`, the id of the comment it answers, and optionally `span`: `[start, end]`, a range of characters in that comment's body |
| Resolution | `resolves`, `author`, `at` |

- A comment without `re` starts a thread, and its anchor has its id. A thread whose anchor
  is gone is an *orphan*.
- A resolution closes the comment it names and every reply below it.
- Readers keep fields they don't know.
- Records are only appended, except by `strip` and by deleting a comment, which only the
  editor offers (see below). A body never changes once written, so a `span` stays valid.
- Removing every marker and the section, which `strip` does, gives back the file as it
  was before any comment, with one exception: a comment on a last line that has no line
  ending leaves one there. Empty lines just above the section go with it, since a
  formatter may add some (ruff wants two before a top-level comment after a function). `strip` removes only markers whose id is a thread's first
  comment in the file, so a marker-shaped example stays even where the reader takes it
  for a marker. It refuses an id with two opening or two closing markers, or a closing
  marker before its opening one, since one may be an example, and it refuses a Python file with a string that is never
  closed, a Markdown section with no closing `-->`, and a section with a line that isn't
  a record, since it can't tell what is safe to remove.

## Reading threads

- Threads come in the order their anchors appear, orphans last. Replies form a tree, each
  comment's replies in the order they were written.
- A comment *waits on* a name when it is a leaf, it is not in a resolved branch, someone
  else wrote it, and it is meant for that name: a person's comment and a comment that
  starts a thread are meant for everyone, and a lemon's reply only for the author of the
  comment it answers. So two lemons answering one person don't wake each other, and a
  reviewer lemon's new thread still reaches the author lemon. A comment whose replies
  were all resolved still counts as answered.
- A duplicate id, a `re` or `resolves` that names no comment, an anchor with no comment,
  a time that isn't UTC, and a line that isn't JSON are errors. lemonaid reports them and
  never rewrites the file to fix them. Threads leave out a comment whose id an earlier
  record used, and any comment in a cycle of replies.

## Reading and writing comments from a shell

`lemonaid comments` reads and writes the threads, so nobody writes the JSON by hand. It
makes each comment's id and timestamp, keeps the file's line endings, and replaces the
file in one step. A write the model refuses leaves the file as it was and exits 2.

```sh
lemonaid comments list <path> [--unanswered (--self | --me <name>)] [--resolved]
lemonaid comments add <path> --lines <a>[-<b>] [--quote <text>] (--self | --as <name>) <body | ->
lemonaid comments reply <path> --re <id> [--after <id>] (--self | --as <name>) <body | ->
lemonaid comments resolve <path> <id> (--self | --as <name>)
lemonaid comments strip <path>
```

- `list` prints each thread's anchored lines and its comments as a tree, and leaves
  resolved branches out unless `--resolved`. With `--unanswered`, it prints only the
  threads with a comment waiting on `--me`, and marks those comments `UNANSWERED`. It
  prints format errors to stderr and exits 1 when there are any.
- `add` and `reply` print the new comment's id. A body of `-` is read from stdin. The
  comments they write are marked as a lemon's (`"by": "lemon"`).
- `--self` signs with the signature the calling lemon's watcher uses for that file, read
  from its brief: the `--me` of a `watch doc` line for the file, else `<name> (Author)` as
  a Docs row has. With `list --unanswered`, it counts that signature as yours. A lemon
  that signs with it can't drift from the name its own waiter matches.
- `reply` to a comment that already has replies needs `--after`, the id of its newest
  reply you have read, and refuses while a newer one exists, printing the comment and the
  replies you haven't read; a first reply needs nothing. Two replies to one comment are
  fine once the second writer has seen the first. The check runs on the text the reply is
  written into, under the writers' lock and through the editor server alike.
- `add --quote` anchors on that text within `--lines`, where it must appear once. Only
  Markdown can anchor part of a line; in Python an anchor covers whole lines.
- A lemon's `add` or `reply --self` also puts a row in the lemonaid inbox, one per
  file and lemon (channel `comments:<lemon's channel>|<path>`), so the person hears of
  it with the file closed. `lma` draws the row right under that lemon, in its groups,
  as `↳ 💬 <file> · N unread`, wherever the lemon's own row is drawn, the other
  terminals' pane included, where Enter on it still opens the file. A row with replies
  to read brings its lemon back into view when the lemon is folded or hidden, and
  shows under a pinned lemon in a collapsed group; a read one folds away with its
  lemon, and one the inbox's fold took stays folded. A row whose lemon is gone, has no
  terminal, or that names none, shows on its own while it has replies to read. The row
  lists the replies the person hasn't seen; the editor marks those unread when the
  file opens and drops each one the person reads, and the row is marked read once it
  lists none. Activating the row opens the file with `lemonaid editor open --focus`,
  or with the system's opener when no editor server answers.
- A write follows a symlink and changes the file it names, whose extension decides its
  kind. If the file changes while a command computes, whether an editor saved it or
  another command wrote it, `reply`, `resolve` and `strip` start again from the new text,
  up to three times, and `add` refuses, since its line numbers may name other code by
  then. A save that lands in the instant between the last check and the replace is still
  lost from the file; the editor holds it unsaved.
- lemonaid's own writers of one file take turns, so two commands never lose each other's
  comment. A command that waits more than five seconds for its turn, such as behind a
  suspended one, refuses and asks you to try again.
- `--lines` counts lines from 1, and the empty line after a file's last line ending is
  not one.
- `--as` and `--me` take the signature a lemon uses in Relay and on GitHub,
  `SleepRib (Author)`. `--me` also counts the spaced spelling, `Sleep Rib (Author)`.
- When an editor running `lemonaid lsp` has the file open and its buffer has unsaved
  changes, a write goes to that buffer instead of the file, and reaches the file when
  you save. A buffer without unsaved changes is left to the editor to reload, and writes
  made before it reloads go to the file too. `list` reads a buffer with unsaved changes,
  so it shows unsaved comments and replies. A write refuses while the buffer and the file
  have both changed since they last matched, until you save or reload, and `add` refuses
  if the buffer changes between the command reading it and the server writing to it. The
  server learns of your typing a moment after you type, so a write in that moment can
  still go to the file; the editor then asks which version to keep.

## The editor server: `lemonaid lsp`

An editor starts `lemonaid lsp` over stdio for its Python and Markdown buffers. It needs
the `lsp` extra: install lemonaid as `lemonaid-inbox[lsp]` (for an editable install,
`uv tool install -e '.[lsp]'`). The server uses full document sync and reparses each
buffer on every change, so it sees what you type before you save. It sends:

- A diagnostic at each anchor, a hint with the author and first line of the thread's
  first comment and its reply count, and an error at each format error.
- `lemonaid/threads`, a notification with `uri`, `version` and `threads`, on open and
  whenever the buffer's comments, resolutions or set of anchors change, and when a client
  asks with `lemonaid.refresh`. An edit that only moves text sends nothing, so a client
  tracks each anchor from where the last notification put it. Each thread has an `anchor`
  range, or `null` for an orphan, and its `comments` in tree order, each with `id`, `re`,
  `span`, `author`, `by` (`lemon` or `person`), `at`, `body`, `resolved` and its `depth`
  below the first comment, and `markers`, the ranges of its own markers, each the `range`
  of what removing it removes and that `text`, for a client that hides them.

Clients write comments through `workspace/executeCommand`, each with one object argument,
and the server answers with `workspace/applyEdit`:

| Command | Argument | Returns |
|---|---|---|
| `lemonaid.comment` | `{uri, range, body}` | `{id}` |
| `lemonaid.reply` | `{uri, re, body, span?, quote?}` | `{id}` |
| `lemonaid.resolve` | `{uri, id}` | `{}` |
| `lemonaid.delete` | `{uri, id}` | `{}` |
| `lemonaid.reanchor` | `{uri, id, range}` | `{}` |
| `lemonaid.refresh` | `{uri}` | `{}`; sends `lemonaid/threads` again |
| `lemonaid.seen` | `{uri, ids}` | `{}`; drops these comments from the file's inbox row, which is marked read once it lists none |

`delete` removes a comment, every reply below it and their resolutions, and for a
thread's first comment its markers too; with the file's last comment, the section goes
as well. `reanchor` moves a thread's markers to the range. Both are the editor's alone:
the socket `lemonaid comments` writes through refuses them, so a lemon can't delete a
comment or move a thread.

A command the server declines fails with LSP's `RequestFailed` (-32803), the reason as
its message, and `data.reason` set for the two a client can act on: `diverged`, the file
changed on disk since the buffer last matched it and no edit went out (reload an
unmodified buffer, then send again; after an edit went out, the reason is null, since a
resend could write the comment twice), and `moved`, the buffer changed while the server
wrote a comment (choose the text again).

A reply's `quote` is the text its `span` covered when you chose it; the server refuses
the reply (`moved`) when the comment no longer says that.

These comments are signed with `[comments] author` from lemonaid's config, else your
login name ([config.md](config.md#comments)). Set it to the name your Relay comments
carry, so a thread names you the same way in code and in a vault.

The server also listens on a socket in lemonaid's state directory (`lsp/<pid>.sock`, with
a record beside it), through which `lemonaid comments` writes to an unsaved buffer and a
lemon reaches your editor:

```sh
lemonaid editor open <path> [--line <n>] [--focus]
lemonaid editor notify <message>
```

`open` asks the server whose workspace holds the path to show it with
`window/showDocument`, or, for a file outside every workspace (a review guide, a note),
the server in the caller's terminal workspace; without `--focus` the cursor stays where
it is. `notify` shows a message. When several servers qualify, the one in the caller's
terminal workspace wins, then the newest. A terminal workspace is a tmux session or a
WezTerm workspace (`front_end.location`); cmux has none, so there only the newest
server counts. With no server, both print why and exit 1.

## The nvim client

lemonaid ships an nvim client beside the server, as a plugin directory that
`lemonaid editor nvim-path` prints. It needs nvim 0.12. Put the directory on
`'runtimepath'`, set it up, and enable the server:

```lua
vim.opt.rtp:append(vim.trim(vim.fn.system({ "lemonaid", "editor", "nvim-path" })))
require("lma").setup({
  -- these are the defaults
  keys = {
    comment = "<leader>cc", resolve = "<leader>cr", thread = "<leader>ct", panel = "<leader>cp",
    delete = "<leader>cx", move = "<leader>cm", autosave = "<leader>cw", unread = "<leader>cu",
    next_unread = "]u", prev_unread = "[u",
  },
  autosave = false, -- save the file after each comment
  -- true in a buffer without threads leaves the comment and panel keys to the
  -- buffer's own mappings, such as another comment plugin's in a vault doc
  yield_to = function(buf) return false end,
})
vim.lsp.enable("lemonaid")
require("lma").start_server() -- so `lemonaid editor open` reaches nvim before a file is open
```

`vim.fn.system` waits for Python to start; to keep startup fast, ask with
`vim.system` and set up in its callback, as enabling after startup attaches the
server to the buffers already open.

- **Threads.** The client lights up the text each thread is about, puts the first
  line of its first comment after it (on a line of its own below when the line would
  wrap), and hides the markers. `:LmaMarkers` shows them again. When a hidden marker is
  no longer where the last notification put it, as after moving one by hand, or the
  notification described an older version of the buffer, the client asks for the
  threads again, at most once per version of the buffer. A Markdown window hides markers only while its `'conceallevel'` is
  above 0, so a renderer that raises it while it draws decides when.
- **Comment.** `<leader>cc` on code opens a small window to write a comment on the
  line or the selection; `:w` sends it and `q` keeps it as a draft. In the panel, the
  same key replies to the comment under the cursor, about the
  selected part of it if there is a selection.
- **Read.** `<leader>cp` opens the panel, every thread of the buffer beside it;
  moving through it lights up each thread's text, and `Enter` jumps there.
  `<leader>ct` on a thread's anchor moves you to that thread in the panel, onto its
  first unread comment if it has one, opening the panel if it is closed.
- **Resolve.** `<leader>cr` resolves the thread under the cursor, or in the panel, the
  comment under the cursor and its replies.
- **Delete.** `<leader>cx` deletes the thread under the cursor, or in the panel, the
  comment under the cursor and its replies, after asking.
- **Move.** `<leader>cm` with a selection moves a thread's anchor to it, asking which
  thread when the file has several.
- **Replies.** A lemon's comment that arrives while you work is unread until you read
  it in the panel: moving the cursor onto it there reads it, and nothing in the file
  does. Its thread's sign shows `●` by the anchor, and in the panel the dot is beside
  each unread comment. A line at the bottom says what arrived and how many comments in
  the file you haven't read, with `lma` yellow while any are, and counts down as you
  read. In the panel, `]u` and `[u` jump to the next or previous unread comment and
  read it; in the file, they jump to the next or previous thread with one.
  `<leader>cu` shows only threads with unread comments in the panel, opening it if it
  is closed, for every buffer until you press it again; a thread you read meanwhile
  stays until you turn the filter off. A reply under a resolved comment is unread too:
  the panel shows the resolved comments around it while you read it. A reply written
  while the file was closed, which its inbox row lists, is unread when the file opens;
  each one you read drops off the row, and the row is marked read once it lists none.
- **Saving.** `<leader>cw` turns on saving the file once the server confirms a comment,
  reply, resolve, delete or move, so a lemon hears of it at once; it is off when nvim
  starts, so a batch of comments goes out on one `:w`. A failed save is reported and
  the comment stays in the buffer.
- **Drafts.** The client saves what you write as you type, in nvim's state
  directory, and deletes it once the server confirms the comment. A refusal, a closed
  window or nvim exiting keeps it, the comment key offers it again on the same file,
  and `:LmaDrafts` lists what is left.
- **A lemon's writes.** The client watches each file the server has open, and reloads
  a buffer without unsaved changes when a lemon writes its file. When the server
  refuses a command because the file changed before nvim noticed (`diverged`), the
  client reloads an unmodified buffer and sends it once more. A comment checks first
  that the text you chose is still there, and asks you to choose it again if not,
  keeping your draft.
- **`lemonaid editor open`** shows the file in a vertical split of the current tab,
  or in the window already showing it, and leaves the cursor where it was unless
  given `--focus`.

## Watching a file for comments

`lemonaid watch doc` reads a Python or Markdown file that has a threads section with
this model, and every doc but a Python file for Relay threads and plain CriticMarkup
comments (`{>>...<<}`), at the same time, so a person can comment either way in one
file; in Python that markup is code, and in Markdown it is ignored inside code. It wakes
a lemon for each new comment waiting on it, by id, and the wake says how to list and
answer them. Markers and the
threads section are not part of the body, so adding a comment or replying is never a body
edit.

## Review guides

The packaged `review-guide` skill ([skills.md](skills.md)) has a lemon write a guide
after each round of changes, ordered for reading, open it with `lemonaid editor open`,
and watch it and the changed files. The lemon answers each comment in its thread with `--self`, leaves
resolving and deleting to you, and before a commit strips the threads and checks that none
is staged.
Put your preferences for guides in `~/.lemons/skills/review-guide/overlay.md`.

## Known limits

- The Markdown reader doesn't follow every container: code inside a list item, and an
  indented code block inside a block quote, are read as text. A marker-shaped example
  there shows up as an anchor with no comment, and `strip` leaves it alone. An example
  that uses a real thread's id can still be taken for the thread's marker: when the
  thread's own marker is gone, or when the example is a closing marker after the
  thread's point marker, which reads as the end of a range.
- In Markdown, a code span that runs over several lines, one of which is exactly
  `<!-- [lma:threads]`, is read as the threads section, and `strip` removes it. Write
  such an example in a fenced block instead.
