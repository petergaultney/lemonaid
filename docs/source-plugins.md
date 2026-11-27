# Watch sources

A watch source lets a lemon follow something lemonaid knows nothing about, the way it follows a PR: `lemonaid watch <source> <args>` under its brief's `## Watching`. The source is a plugin, a command that reads the outside thing; lemonaid keeps the scheduling, the cursors, batching, delivery and ack-after-delivery, and ends a subscription when the plugin says so.

[Slack](slack.md) is the source configured by default. It ships in the same package as lemonaid (`lemonaid-slack`, with the `slack` extra for its socket and sign-in window) but talks to it only through the protocol below; neither imports the other.

## Configuring sources

```toml
[[watch.sources]]
name = "slack"
command = "lemonaid-slack"

[[watch.sources]]
name = "tickets"
command = "/opt/bin/ticket-source --project ops"
```

With no `[[watch.sources]]` entry, lemonaid runs Slack alone. A list replaces that default, so include `slack` to keep it; `[watch] sources = []` turns every source off.

- `name` is the word after `lemonaid watch`, the `kind` that `watch stop` takes, and the directory under each lemon's cursors. It is lowercase letters, digits and dashes, and can't be one of lemonaid's own `watch` subcommands (`pr`, `doc`, `stop` and the rest).
- `command` is split as a shell would split it, but no shell runs it. A bare program name installed in lemonaid's own environment is found there.
- The config file's top-level table named for the source (`[slack]`, `[tickets]`) is the plugin's own; lemonaid passes it along without reading it.
- `lemonaid <name> <args>` runs `<command> <args>`, so a plugin's own commands (`lemonaid slack signin`) need no lemonaid code. A name lemonaid already uses as a command isn't given one.

## What a plugin is given

Each lemonaid process that runs scouts (the scout host, or a waiter in the foreground) starts each source's plugin once, on first use, and shares it among all its subscriptions. The plugin keeps running until lemonaid closes its stdin. Its environment adds:

| Variable | Value |
|---|---|
| `LEMONAID_PLUGIN_STATE` | A directory of its own, `$LEMONAID_STATE_DIR/<name>`. It may not exist yet. |
| `LEMONAID_PLUGIN_CONFIG` | Its config table, as JSON; `{}` when there is none. |
| `LEMONAID` | The command that runs this lemonaid, shell-quoted, for host commands such as `lemonaid inbox add` ([inbox rows](inbox-items.md)). |

The same variables are set for `lemonaid <name> ...`. Several lemonaid processes may run the plugin at once, so anything it must do once per machine (Slack's socket) needs its own lock.

## The protocol

The plugin's first line on stdout is `lemonaid-source-plugin 1`. Then it serves requests on stdin, one at a time, framed as every lemonaid plugin's are:

```text
-> <header>                    such as `poll 3f2a9c1d`
-> <field> <value>             any number of them
-> text <n>                    then exactly n bytes, UTF-8
<- ok <n>                      then exactly n bytes of the answer, UTF-8
<- error <message>
```

Any other line the plugin writes, at any time, even while lemonaid waits for an answer, is a notice. The only notice lemonaid reads is `ready <id>`: subscription `<id>` has something new, so poll it now. What the plugin writes on stderr goes to lemonaid's stderr.

### `check`

Fields: one `arg <word>` per argument after `lemonaid watch <name>`, in order, without lemonaid's own `--me` and `--once`. Text: empty.

Answer one `target <word>` line per word naming what the arguments follow, such as a Slack thread's channel and ts. Two argument lists that follow the same thing (two links to one thread) must give the same target: lemonaid keys a lemon's subscription, its cursor file (`<target words joined by ->.json`) and `watch stop`'s target by it. For arguments that name nothing, answer `error <usage message>`; lemonaid reports it as a problem with the brief's line.

lemonaid asks `check` whenever it reads a brief, so it must be cheap and depend only on its arguments: no network.

### `poll <id>`

`<id>` is lemonaid's name for one subscription of one lemon, kept for as long as it follows it. Fields: the `arg` lines, as for `check`; `follower <name>`, the lemon's cursor key; and `done yes` once the lemon's brief is `done`. Text: the cursor the last answer gave, or empty before the first.

Answer with records, each a line `<record> <value>` followed by its field lines:

| Record | Meaning |
|---|---|
| `cursor <json>` | Where the next poll starts: one line, by convention a JSON object. lemonaid stores it only after the wake in the same answer is delivered, and gives it back unchanged. Leave it out when the poll could not read the source; the cursor then stays where it was. |
| `wake` | Something to tell the lemon. Fields: `text <line>`, one per line of the message; `label <line>`, a few words for a one-line summary; `count <n>`, how many events it holds. |
| `end <sentence>` | The subscription is over, such as `Stopped following Slack thread <link>: your brief is done`. lemonaid tells the lemon once, adding that the line left `## Watching`, removes every `## Watching` line with the same target, deletes the cursor and sends `forget`. Field: `label`. |
| `problem <sentence>` | The source can't be read until someone acts, such as a sign-in. The lemon hears it once per lapse: not again until a poll returns a `cursor`. Field: `label`. |
| `every <seconds>` | Poll again after this long without a `ready`. Without it, lemonaid polls again after an hour. |

lemonaid ignores lines it does not know, so a plugin may print fields a later version will read. A plugin that answers `error`, or fails, is polled again after 10 seconds. One that exits is started again then, and every subscription is polled at once, so the new process learns each id before it is asked for `ready` notices.

### `forget <id>`

The subscription is gone: the lemon stopped following it, its scout stopped, or it ended. Answer `ok 0`. A plugin should stop any work it did for that id.

## Testing a source

`tests/sources/fake_source.py` is a complete source with no lemonaid imports, and `tests/sources/test_watching.py` runs lemonaid's poller against it. Talk to your own by hand the way lemonaid does:

```sh
printf 'check\narg item:news\ntext 0\n' | my-source
```
