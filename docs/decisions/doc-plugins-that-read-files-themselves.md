---
type: Design
status: draft
---

# Document plugins that read files themselves

Version 1 of the [document plugin protocol](../doc-plugins.md) sends the plugin the whole document on every change and asks it for a body and a list of threads. lemonaid then diffs the body, keeps the cursors and decides what wakes a waiter. That suits a comment format, which is a parser: a pure function of the text.

Some future plugins will not fit that shape. This note records an alternative for them, so a second protocol version can be designed from it rather than from scratch. Nothing here is built.

## Where version 1 does not fit

- **Large files.** The text crosses the pipe twice per plugin per change, and each answer is held in lemonaid's result cache. A 50 MB file costs about 5 seconds of Relay parsing per change and a document-sized copy in memory per cached answer.
- **Plugins that only need to know a file changed.** A plugin that indexes a file, reruns a check or forwards a notice has no body to give and no use for lemonaid's diff.
- **Files that are not text,** or watches that are not one file: a SQLite database, a PDF, a directory of results.
- **Answers that depend on history.** Version 1 constrains the answer, not how it is computed: a plugin may keep a parse tree and reparse only the changed region, as long as each answer matches parsing that snapshot from scratch. What it cannot express is an answer whose meaning depends on earlier snapshots or other state the request doesn't carry, such as "this section moved since you last looked."

## The alternative: tell the plugin which file changed

lemonaid still notices the change (by polling, as now) and still owns quiet periods, cursors and delivery. What crosses the pipe is a path, not the text:

```text
changed /notes/plan.md
name Mo (Author)
```

The plugin reads the file itself, compares it with whatever it kept from last time, and answers with the same `threads` records version 1 uses. Thread keys, `waiting`, `note` and `incomplete` keep their meanings, so lemonaid's cursors, reminders and failure rules carry over unchanged. A plugin with nothing to report as threads could instead answer with wake text directly.

A plugin would choose this mode at hello, for example `lemonaid-doc-plugin 2 path-only`, so version 1 plugins keep working beside it.

## What lemonaid gives up

- **A shared snapshot.** In version 1 every plugin sees exactly the bytes lemonaid read. A plugin reading the file itself may see a later write, so two plugins can disagree about one change.
- **Body edits and own-edit attribution.** Both compare a comment-free body that lemonaid computes. A path-only plugin gives no body, so a watch using only such plugins reports no body edits, and a lemon's own edit cannot be told apart from anyone else's unless the plugin tracks that itself.
- **Caching by request.** A version 1 answer depends only on its request, so lemonaid reuses it for every waiter and every poll of an unchanged file. A stateful plugin's answer depends on its history, so lemonaid must ask once per change and share that answer among waiters itself.
- **Easy testing.** A pure plugin is tested by piping a file into it; a stateful one needs a sequence of changes.

## Relation to watch-source plugins

A plugin that watches files on its own, with no polling by lemonaid at all, is a watch source rather than a document plugin: it reports events between requests as notices, through the same process model in `src/lemonaid/plugins/`. If path-only document plugins turn out to need neither lemonaid's polling nor its quiet periods, they should be watch sources instead of a second document protocol.
