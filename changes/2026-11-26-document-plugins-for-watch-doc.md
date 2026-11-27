# Minor

#### Added

- **`watch doc` reads comments through document plugins.** A plugin is a long-running command that answers requests for a document's threads, and its body without comments, in a line-oriented protocol on stdin and stdout, configured under `[[watch.doc.plugins]]` (see `docs/doc-plugins.md`). Relay Comments is now the default plugin, `lemonaid-relay-comments`; existing waiters, cursors and own-edit records keep working with no config change.
- **Watch sources: `lemonaid watch <name>` follows anything a plugin can read.** A source is a long-running command configured under `[[watch.sources]]`; lemonaid keeps the scheduling, cursors, delivery and ending of each subscription, and `lemonaid <name> ...` runs the plugin's own commands. The protocol is in `docs/source-plugins.md`.
- **A tool can keep an inbox row under a lemon.** `inbox add --under <lemon channel>` draws the row right under that lemon, wherever it is drawn, and `--hide-when-read` drops it once read; `inbox read --channel` marks it read by channel. See `docs/inbox-items.md`.
- **`[inbox.openers]` names commands a row's Enter may run on its file.** A row asks for one with `opener` and `path` metadata, and falls back to its `open_uri`.
- **`skills install` installs skills from other sources.** A `[[skills.sources]]` entry names a directory of skills by `path`, by a `command` that prints it, or by a `fetch` command that fills one lemonaid keeps; a source's `skills.toml` can mark skills `optional`. `lemonaid skills list` shows where each skill comes from.
- **`watch doc --signature <doc>` prints the name your own waiter on a doc counts as yours,** so a tool that writes your replies signs with it.

#### Changed

- **A Docs row's Watch value is `Comments`.** `Relay comments`, its old name, still reads as `Comments`, and new rows are written with the new name.
- **Slack is now a watch source, `lemonaid-slack`, configured by default.** `lemonaid watch slack`, `lemonaid slack signin|status|signout` and the `[slack]` table work as before, and existing cursors carry over. A lemon that is told Slack needs a sign-in when you upgrade may hear it once more.
