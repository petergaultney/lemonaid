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

## Core changes it would still need

- **Inbox reply rows.** `comments/notice.py` writes `comments:<lemon>|<path>` rows straight into the inbox database, and the inbox and grove special-case that prefix (`inbox/sections.py`, `inbox/tui/live/*`, `grove/source/inbox_keys.py`). `handlers.py` opens such a row with `python -m lemonaid editor`. A plugin needs a generic inbox item instead: keyed upsert and acknowledgement through the CLI, an owning lemon to group under, and an activation command declared in config rather than imported. This is the largest piece.
- **The caller's signature.** `comments.cli.own_signature` reads the brief and its watch subscriptions to find the name a lemon signs with for a file. A plugin needs that from a host command, such as `lemonaid watch doc --signature <doc> --self`, rather than importing `brief` and `subscriptions`.
- **Skills from a plugin.** `review-guide` is a packaged skill, and the skill installer only renders packaged names. A plugin needs a way to register its own skill directory with `lemonaid skills install`. The Relay reply format has the same gap: it is still taught by the packaged `watch-doc` skill.
- **Not needed:** the `lemonaid comments`, `lsp` and `editor` subcommands can be the plugin's own executable; `file.py`'s atomic write is small enough to copy.

## What the interface leaves out on purpose

Plugins are commands with a line protocol, not Python entry points, as with place hooks: a plugin may live in its own environment or language, and core never imports it. Each plugin runs as one long-lived process per lemonaid process, so a parser with a slow start, such as one that imports a Markdown library, pays that cost once rather than on every changed snapshot. Results are also kept by a digest of their request, so polling an unchanged document asks nothing.
