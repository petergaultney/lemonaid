# Document plugins

`lemonaid watch doc` knows no comment format. A document plugin is a command that finds the comment threads in a document and removes them from its body; lemonaid runs every configured plugin on each snapshot it reads and does the rest: polling, quiet periods, cursors, delivery, own-edit attribution and brief bookkeeping.

[Relay Comments](#relay-comments) is the plugin configured by default. It ships in the same package as lemonaid (`lemonaid-relay-comments`) but talks to it only through the protocol below; neither imports the other.

## Configuring plugins

```toml
[[watch.doc.plugins]]
name = "relay-comments"
command = "lemonaid-relay-comments"

[[watch.doc.plugins]]
name = "my-format"
command = "/opt/bin/my-format --strict"
```

With no `[[watch.doc.plugins]]` entry, lemonaid runs Relay Comments alone. A list replaces that default, so include `relay-comments` to keep it; `[watch.doc] plugins = []` turns every plugin off, and `watch doc` then reports body edits only.

- `name` keys the plugin's threads in each waiter's saved cursor. Changing it makes waiters report that plugin's unanswered threads once more.
- `command` is split as a shell would split it, but no shell runs it. A bare program name installed in lemonaid's own environment is found there, so waiters need no PATH that includes it.
- Order matters for the body: each plugin removes its comments from what the plugin before it left. Every plugin reads the same original text for threads.

## The protocol

A plugin is a long-running process. lemonaid starts it once, the first time a lemonaid process (a waiter, the scout host, the inbox) needs it, and sends it one request at a time on stdin; the plugin answers each on stdout. Closing stdin means exit. stderr goes to lemonaid's own stderr, so a waiter's log shows it.

The plugin's first line, before any request, is its version:

```text
lemonaid-doc-plugin 1
```

A request names the operation and the document, then the reader's names (for `threads`), then the document's text as a counted run of UTF-8 bytes, with LF line endings: exactly the snapshot lemonaid read.

```text
threads /notes/plan.md
name Mo (Author)
name Mo
text 1234
<1234 bytes of the document>
```

The answer is `ok <n>` and exactly n bytes of UTF-8, the operation's result below, or a one-line `error <message>`:

```text
ok 57
<57 bytes>
```

Any other line the plugin writes is a notice, which other kinds of plugin use to report events between requests; lemonaid ignores notices from a document plugin, and keeps waiting for the answer. The process model and framing live in `src/lemonaid/plugins/`, shared by every kind of plugin.

The path names the document; use it to decide the format (a `.py` file, say), not to read the file again. A result must depend only on the request: lemonaid keeps the latest result for each document, operation and reader with a digest of the text, so a waiter that reads an unchanged document every second asks nothing.

A plugin that doesn't say hello, answers `error`, exits, or takes more than 10 seconds to start or to answer fails that call (see [Failures](#failures)); lemonaid closes it and starts it again on a later call, no sooner than 10 seconds after the failure, so a broken plugin isn't started on every poll. A failure is printed once, when it happens.

### `body`

Answer with the text with this plugin's comments removed: the prose people wrote, which lemonaid compares to report body edits and to recognize a lemon's own edits. A plugin that finds none of its comments answers with the text unchanged. Keep any text a comment highlights, as Relay does; the body is only compared and diffed, never written back.

### `threads`

The request's `name` lines are the reader: every spelling of its signature and its `--legacy` names. Answer with one record per thread, each a `thread` line followed by its fields, one `<field> <value>` per line:

```text
thread 3f2a9c1d
last Sam Rivera
waiting
gist Sam Rivera: is this true?
text Sam Rivera:
text is this true?
note Reply by appending a block after the thread's last one.
```

| Line | Meaning |
|---|---|
| `thread <key>` | Starts a thread. The key has no spaces and changes whenever the thread does (a new reply, an edited comment), so a changed thread wakes the reader again. Keys need only be unique within the plugin. |
| `last <author>` | Who wrote last, as the document names them. Stalled-review detection uses it to see whether a PR's author or reviewer answered last. |
| `waiting` | The thread waits on the reader named by the call's names. The plugin decides what that means: Relay says a thread waits when its last block is not signed with one of the names. |
| `text <line>` | The comment to show in the wake, one line each; lines join with newlines. Cut it to a size you choose; lemonaid cuts a whole wake at 30000 characters. |
| `gist <line>` | One line for a reminder of a thread already reported. Default: the text on one line, cut to 100 characters. |
| `note <line>` | Anywhere: a line shown ahead of this plugin's new threads in a wake, such as how to answer them. |
| `incomplete` | Anywhere: the plugin could not read every thread, so a thread missing from this reading may still be there. |

lemonaid ignores lines it does not know, so a plugin may print fields a later version will read.

### Failures

A failed `body` call means lemonaid has no body for that snapshot: the poll reports no body edit and settles nothing, and a lemon's own-edit hook records nothing, so the edit wakes its waiter once rather than being missed. Linked brief questions and task facts fall back to the text with its comments in it.

A failed `threads` call reads as `incomplete` with no threads. lemonaid keeps every key that plugin reported before, so a thread is not reported again when the plugin recovers, and delivers nothing new from it. A complete reading drops the keys of threads that no longer wait, so a thread that waits again is reported again.

## What lemonaid does with the results

- **A wake** lists each plugin's new waiting threads (notes first), then, under `watch --self`, reminders of ones already reported. The cursor advances only after the wake is delivered.
- **Body edits** compare the plugins' body with the body as last reported, after the quiet period. A lemon's own edits are recorded as digests of that same body.
- **Brief readers**: a Needs bullet that links to a heading shows that section's body; a task's file facts list headings found in the body.
- **Stalled reviews** read `last` from every plugin's threads.

## Relay Comments

The [Relay](https://relay.md) Obsidian plugin writes a thread as an optional `{==highlight==}` followed by blocks `{{authorId="..." author="...">>text<<}}` with nothing in between. A thread waits on the reader until its last block's `author` (else `authorId`) is one of the reader's names. Its body keeps highlighted text and removes the blocks. Its keys are the same digests waiters saved before Relay was a plugin, so an upgrade reports nothing twice. The reply format lemons follow is in the packaged `watch-doc` skill.

## Testing a plugin

`tests/doc_plugins/fake_plugin.py` is a complete plugin in plain Python with no lemonaid imports, and `tests/doc_plugins/test_watching.py` runs `watch doc` with it. Talk to your own by hand the way lemonaid does:

```sh
{ printf 'body notes.md\ntext %s\n' "$(wc -c < notes.md)"; cat notes.md; } | my-format
```
