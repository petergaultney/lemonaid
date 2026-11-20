# Minor

#### Added

- **Review comments kept in the file they are about.** Anchor markers in the body and an append-only section of JSON lines at the end of the file hold threaded comments in Python and Markdown files; `docs/comments.md` describes the format.
- **`lemonaid comments`** lists a file's threads with their code, and adds, replies to, resolves and strips comments, so a lemon never writes the JSON itself.
- **`lemonaid watch doc` reads comments kept in the file.** For a Python or Markdown file with a threads section, it wakes a lemon for each new unanswered comment and says how to answer it; adding a comment or replying is not a body edit.
- **`lemonaid lsp`, a language server for review comments** (the `lsp` extra). It marks each thread and format error with a diagnostic, sends `lemonaid/threads` for clients to draw threads from, and adds, replies to and resolves comments in the buffer, signed with the new `[comments] author`. `lemonaid comments` writes to a buffer with unsaved changes through it.
- **`lemonaid editor open` and `notify`** open a file or show a message in the editor running `lemonaid lsp`: the one whose workspace holds the file, else the one in your terminal workspace (tmux session or WezTerm workspace).
- **An nvim client for review comments**, shipped in the package; `lemonaid editor nvim-path` prints its plugin directory. It draws threads, comments, replies and resolves through the server, keeps drafts until the server confirms them, and reloads a buffer when a lemon writes its file.
