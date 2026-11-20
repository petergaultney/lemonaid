# Minor

#### Added

- **Review comments kept in the file they are about.** Anchor markers in the body and an append-only section of JSON lines at the end of the file hold threaded comments in Python and Markdown files; `docs/comments.md` describes the format.
- **`lemonaid comments`** lists a file's threads with their code, and adds, replies to, resolves and strips comments, so a lemon never writes the JSON itself.
- **`lemonaid watch doc` reads comments kept in the file.** For a Python or Markdown file with a threads section, it wakes a lemon for each new unanswered comment and says how to answer it; adding a comment or replying is not a body edit.
