# Minor

#### Added

- **Review comments kept in the file they are about.** Anchor markers in the body and an append-only section of JSON lines at the end of the file hold threaded comments in Python and Markdown files; `docs/comments.md` describes the format.
- **`lemonaid comments`** lists a file's threads with their code, and adds, replies to, resolves and strips comments, so a lemon never writes the JSON itself. `--self` signs with the name the lemon's watcher counts as its own for that file; a reply to a comment that already has replies names the newest it read with `--after`, so a lemon doesn't repeat an answer someone just gave; `add --quote` anchors a phrase in Markdown. A lemon's comment also shows in the inbox, in a row under that lemon for each file, until the person has seen it.
- **`lemonaid watch doc` reads comments kept in the file.** For a Python or Markdown file with a threads section, it wakes a lemon for each new comment waiting on it and says how to answer it; adding a comment or replying is not a body edit. Relay and plain CriticMarkup comments in the same file wake it too. A lemon's reply to a person wakes only the person, not other lemons on the file.
- **`lemonaid lsp`, a language server for review comments** (the `lsp` extra). It marks each thread and format error with a diagnostic, sends `lemonaid/threads` for clients to draw threads from, and adds, replies to and resolves comments in the buffer, signed with the new `[comments] author`. `lemonaid comments` writes to a buffer with unsaved changes through it.
- **`lemonaid editor open` and `notify`** open a file or show a message in the editor running `lemonaid lsp`: the one whose workspace holds the file, else the one in your terminal workspace (tmux session or WezTerm workspace).
- **The `review-guide` skill.** After each round of changes, a lemon writes a guide that orders them for reading, opens it in your editor, watches it and the changed files, answers your comments in their threads, and keeps comments out of commits. Your guide preferences go in its overlay.
- **An nvim client for review comments**, shipped in the package; `lemonaid editor nvim-path` prints its plugin directory. It draws threads, comments, replies, resolves, deletes and moves them through the server, keeps drafts until the server confirms them, reloads a buffer when a lemon writes its file, announces a lemon's reply and marks it unread until you read it in the panel, counts what you haven't read, shows only threads with unread comments in its panel (`<leader>cu`) and jumps between unread comments (`]u`, `[u`), and can save the file after each comment (`<leader>cw`). Deleting and moving a thread are the editor's alone.

#### Changed

- **The `Comments` watch mode** replaces `Relay comments` in a brief's Docs table, since it covers threads kept in the file too. `Relay comments` still reads as `Comments`.
