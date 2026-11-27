---
type: Design
status: draft
---

# In-file comments (#570) as a document plugin

[lemonaid#570](https://github.com/petergaultney/lemonaid/pull/570) keeps review threads inside Python and Markdown files, with a CLI, a language server and an nvim client. This note maps its watcher integration onto the [document plugin interface](../doc-plugins.md) and names the core changes it would still need.

**Short answer:** its watching needs no core change. Everything #570 changed in `watch/doc_events.py`, `watch/file_comments.py`, `watch/own_edits.py` and `watch/relay_comments.py` becomes a plugin command plus edits inside the Relay plugin. Its inbox reply rows and its `review-guide` skill do need core changes, because they are not document watching.

## Watching: no core change

| What #570 does in core | As a plugin |
|---|---|
| `file_comments.document` / `unanswered`: comments in a file's threads section that wait on `--me` | `threads`: one record per waiting or answered comment. `waiting` follows `threads.unanswered`, including its rule that a lemon's reply waits only on the author it answers; the plugin owns that rule. |
| `file_comments.key`: `lma:<id>:<digest>` | The `thread` key as is. It has no spaces, and keys are namespaced by plugin name, so the `lma:` prefix is no longer needed but does no harm. |
| `comment_text`, `comment_gist` | `text` lines and `gist`. |
| `how_to_answer`, placed ahead of the comments so a cut wake keeps it | `note` lines, which core already puts ahead of the plugin's new threads. #570 lists only the new ids; a note lists what the plugin chooses, so it can name every waiting id. |
| `_still_reported`: keep `lma:` keys while the file has no threads section | Print `incomplete` when no section could be read. Core keeps that plugin's reported keys, which is the same rule. |
| `file_comments.body`: remove owned markers and the section, then Relay blocks | `body` removes markers and the section. List the in-file plugin before `relay-comments` in `[[watch.doc.plugins]]`, and core feeds Relay what it left, as #570 does by hand. |
| Python files skip Relay; Markdown code regions hide Relay examples; plain `{>>..<<}` comments | Changes to the Relay plugin only (`src/lemonaid_relay_comments/`), keyed on the path it is given. |
| `own_edits._file_digest` reads the same body | Already the plugins' body; nothing to do. |
| Docs label `Relay comments` -> `Comments`, old name still read | Done in this change. |

One difference to check when porting: the protocol gives a plugin LF text, as `watch doc` reads it. #570's `read` keeps CRLF so the watcher and `lemonaid comments` find the same section. If its parser needs the original line endings to find the section, it must accept LF input for watching; the editing commands still read the file themselves.

## Its other core changes, as host commands

Three things #570 did in core are not document watching. Each now has a generic host command, so the plugin needs no core change for them either:

- **Inbox reply rows.** `comments/notice.py` wrote `comments:<lemon>|<path>` rows into the database, and the inbox special-cased that prefix. The plugin now runs `lemonaid inbox add <channel> <message> -n <label> --under <lemon channel> --hide-when-read --metadata '{"opener": "editor", "path": ..., "open_uri": ...}'` and `lemonaid inbox read --channel <channel>`; the drawing is #570's layout, keyed on `under` ([inbox rows for a lemon](../inbox-items.md)). Opening the file in its editor is an `[inbox.openers]` entry the user configures, replacing the `python -m lemonaid editor` call in `handlers.py`. The lemon's channel comes from `lemonaid brief id --self --json`.
- **The caller's signature.** `lemonaid watch doc --signature <doc>` prints what `comments.cli.own_signature` computed.
- **Skills.** The plugin lists its skill directory under `[[skills.sources]]` (or prints it from a `command`), with `review-guide` marked `optional` in its `skills.toml` ([skills from other sources](../skills.md#skills-from-other-sources)).

The `lemonaid comments`, `lsp` and `editor` subcommands become the plugin's own executable, and `file.py`'s atomic write is small enough to copy.

## What the interface leaves out on purpose

Plugins are commands with a line protocol, not Python entry points, as with place hooks: a plugin may live in its own environment or language, and core never imports it. Each plugin runs as one long-lived process per lemonaid process, so a parser with a slow start, such as one that imports a Markdown library, pays that cost once rather than on every changed snapshot. Results are also kept by a digest of their request, so polling an unchanged document asks nothing.
