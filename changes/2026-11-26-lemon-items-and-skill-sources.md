# Minor

#### Added

- **A tool can keep an inbox row under a lemon.** `inbox add --under <lemon channel>` draws the row right under that lemon, wherever it is drawn, and `--hide-when-read` drops it once read; `inbox read --channel` marks it read by channel. See `docs/inbox-items.md`.
- **`[inbox.openers]` names commands a row's Enter may run on its file.** A row asks for one with `opener` and `path` metadata, and falls back to its `open_uri`.
- **`skills install` installs skills from other sources.** A `[[skills.sources]]` entry names a directory of skills by `path`, by a `command` that prints it, or by a `fetch` command that fills one lemonaid keeps; a source's `skills.toml` can mark skills `optional`. `lemonaid skills list` shows where each skill comes from.
- **`watch doc --signature <doc>` prints the name your own waiter on a doc counts as yours,** so a tool that writes your replies signs with it.
