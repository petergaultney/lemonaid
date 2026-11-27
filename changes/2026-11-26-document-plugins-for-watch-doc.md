# Minor

#### Added

- **`watch doc` reads comments through document plugins.** A plugin is a long-running command that answers requests for a document's threads, and its body without comments, in a line-oriented protocol on stdin and stdout, configured under `[[watch.doc.plugins]]` (see `docs/doc-plugins.md`). Relay Comments is now the default plugin, `lemonaid-relay-comments`; existing waiters, cursors and own-edit records keep working with no config change.

#### Changed

- **A Docs row's Watch value is `Comments`.** `Relay comments`, its old name, still reads as `Comments`, and new rows are written with the new name.
