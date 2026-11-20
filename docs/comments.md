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
- lemonaid writes inline Markdown markers around the selected text, trimmed of
  whitespace at its ends. It writes the own-line spelling around a fenced block and on a
  line that holds only markers, where an inline marker would change what the others
  remove. It never writes inside an existing marker or between a CR and its LF.
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
| Comment | `id`, `author`, `at` (ISO 8601, with a UTC offset of zero), `body` (Markdown) |
| Reply | a comment with `re`, the id of the comment it answers, and optionally `span`: `[start, end]`, a range of characters in that comment's body |
| Resolution | `resolves`, `author`, `at` |

- A comment without `re` starts a thread, and its anchor has its id. A thread whose anchor
  is gone is an *orphan*.
- A resolution closes the comment it names and every reply below it.
- Readers keep fields they don't know.
- A body never changes once written, so a `span` stays valid.
- Removing every marker and the section, which `strip` does, gives back the file as it
  was before any comment, with one exception: a comment on a last line that has no line
  ending leaves one there. `strip` removes only markers whose id is a thread's first
  comment in the file, so a marker-shaped example stays even where the reader takes it
  for a marker. It refuses an id with two opening or two closing markers, or a closing
  marker before its opening one, since one may be an example, and it refuses a Python file with a string that is never
  closed, a Markdown section with no closing `-->`, and a section with a line that isn't
  a record, since it can't tell what is safe to remove.

## Reading threads

- Threads come in the order their anchors appear, orphans last. Replies form a tree, each
  comment's replies in the order they were written.
- A comment is *unanswered* for a name when it is a leaf, it is not in a resolved branch,
  and someone else wrote it. A comment whose replies were all resolved still counts as
  answered.
- A duplicate id, a `re` or `resolves` that names no comment, an anchor with no comment,
  a time that isn't UTC, and a line that isn't JSON are errors. lemonaid reports them and
  never rewrites the file to fix them. Threads leave out a comment whose id an earlier
  record used, and any comment in a cycle of replies.

## Reading and writing comments from a shell

`lemonaid comments` reads and writes the threads, so nobody writes the JSON by hand. It
makes each comment's id and timestamp, keeps the file's line endings, and replaces the
file in one step. A write the model refuses leaves the file as it was and exits 2.

```sh
lemonaid comments list <path> [--unanswered --me <name>] [--resolved]
lemonaid comments add <path> --lines <a>[-<b>] --as <name> <body | ->
lemonaid comments reply <path> --re <id> --as <name> <body | ->
lemonaid comments resolve <path> <id> --as <name>
lemonaid comments strip <path>
```

- `list` prints each thread's anchored lines and its comments as a tree, and leaves
  resolved branches out unless `--resolved`. With `--unanswered`, it prints only the
  threads with a comment waiting on `--me`, and marks those comments `UNANSWERED`. It
  prints format errors to stderr and exits 1 when there are any.
- `add` and `reply` print the new comment's id. A body of `-` is read from stdin.
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
  whenever the buffer's comments, resolutions or set of anchors change. An edit that only
  moves text sends nothing, so a client tracks each anchor from where the last
  notification put it. Each thread has an `anchor` range, or `null` for an orphan, and
  its `comments` in tree order, each with `id`, `re`, `span`, `author`, `at`, `body`,
  `resolved` and its `depth` below the first comment, and `markers`, the ranges of its
  own markers, each the `range` of what removing it removes and that `text`, for a
  client that hides them.

Clients write comments through `workspace/executeCommand`, each with one object argument,
and the server answers with `workspace/applyEdit`:

| Command | Argument | Returns |
|---|---|---|
| `lemonaid.comment` | `{uri, range, body}` | `{id}` |
| `lemonaid.reply` | `{uri, re, body, span?, quote?}` | `{id}` |
| `lemonaid.resolve` | `{uri, id}` | `{}` |

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
  keys = { comment = "<leader>cc", resolve = "<leader>cr", thread = "<leader>ct", panel = "<leader>cp" },
  -- true in a buffer without threads leaves the comment and panel keys to the
  -- buffer's own mappings, such as another comment plugin's in a vault doc
  yield_to = function(buf) return false end,
})
vim.lsp.enable("lemonaid")
```

`vim.fn.system` waits for Python to start; to keep startup fast, ask with
`vim.system` and set up in its callback, as enabling after startup attaches the
server to the buffers already open.

- **Threads.** The client lights up the text each thread is about, puts the first
  line of its first comment after it, and hides the markers. `:LmaMarkers` shows
  them again. A Markdown window hides markers only while its `'conceallevel'` is
  above 0, so a renderer that raises it while it draws decides when.
- **Comment.** `<leader>cc` on code opens a small window to write a comment on the
  line or the selection; `:w` sends it and `q` keeps it as a draft. In the panel or a
  thread float, the same key replies to the comment under the cursor, about the
  selected part of it if there is a selection.
- **Read.** `<leader>cp` opens the panel, every thread of the buffer beside it;
  moving through it lights up each thread's text, and `Enter` jumps there.
  `<leader>ct` shows the thread under the cursor in a float, and pressing it again
  moves into the float.
- **Resolve.** `<leader>cr` resolves the thread under the cursor, or in the panel or
  a float, the comment under the cursor and its replies.
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
this model, and any other doc for Relay Comment threads. It wakes a lemon for each new
unanswered comment, by id, and the wake says how to list and answer them. Markers and the
threads section are not part of the body, so adding a comment or replying is never a body
edit.

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
