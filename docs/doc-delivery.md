# Doc delivery

A lemon needs a rule when it is about to do the thing the rule governs, not only when its
session starts. Lemonaid lets each doc say, in its own frontmatter, which lemons get it at
session start and which actions bring it back. The docs live under the folders and files
[`[docs] roots`](config.md#docs) lists.

What a lemon is given depends on its [docs mode](config.md#docs):

- A `packages` lemon gets the packages that are for it in place of the always-loaded
  docs, and every trigger that matches.
- A `classic` lemon keeps the always-loaded docs, and gets only the packages and
  triggers that name its group or its lead ([below](#rules-for-a-group-or-a-leads-lemons)).
  Every other delivery is logged as `shadow`, without giving it, so the two modes can
  be compared.

## Packages: what a lemon gets at session start

A package is a doc whose frontmatter has `package-for`, the lemons it is for. Its name is
its file name without `.md`:

```yaml
# packages/python.md
---
package-for:
  - file: pyproject.toml
---
```

A doc joins a package by naming it, so it keeps its package when it moves:

```yaml
---
package: python          # or a list: [author, reviewer]
---
```

A package is for a lemon when any item of its `package-for` matches, and an item matches
when all of its keys do:

| Key | Matches |
|---|---|
| `cwd` | A glob on the session's working directory, such as `~/src/app/**`. |
| `brief` | `true` for a lemon with an attached brief, `false` for one without. |
| `brief-text` | A regex found in the attached brief. |
| `file` | A file name in the working directory or a folder above it. |
| `branch` | `not-default`: [`[docs] default-branch-check`](config.md#docs) fails in the working directory. Without that setting it matches nothing. |
| `group` | The lemon is in that lemonaid group. |
| `under` | The lemon descends from that Lemon-ID, or a lemon with that name, through parent links of any depth. |
| `not` | An item that must not match. |

`{}` matches every lemon. An unknown key matches no lemon, and is logged.

## Triggers: what brings a doc back

`load-when` lists the actions that deliver a doc, or one of its sections:

```yaml
---
load-when:
  - command: '^gh pr (create|ready)\b'
    section: Draft and ready
    before: true
  - edit: 'docs/**/*.md'
reminder: Open every PR as a draft.
---
```

| Kind | Matches |
|---|---|
| `command` | A regex searched in each simple command of a shell call, after splitting at `&&`, `\|\|`, `;`, `\|` and newlines and dropping leading `NAME=value` assignments. The split ignores quoting. |
| `edit` | A glob on a file the call writes: a Claude Code file tool's path, or a file a Codex patch adds, updates or moves to. |
| `create` | The same, for a file the call creates. |
| `prompt` | A regex searched in the user's message. |

A glob's `*` and `?` stay within one folder and `**` crosses folders. A glob starting with
`/` or `~` matches from the root, and any other matches at any depth, so `*.py` matches
every Python file.

- `section` delivers only the part of the doc under that heading, up to the next heading
  at its level. Without it, the whole doc is delivered, less its frontmatter.
- `before: true` is for a rule about the call itself. Context a hook adds reaches the model
  after the call has run, so its first match in each context window refuses the call,
  with the section as the reason, even when a package already gave the lemon the doc.
  The next call goes through. Only a tool call is refused; a `prompt` or Claude Code
  `create` match gives the section as context instead.
- The `package-for` keys, such as `group`, limit a trigger to the lemons they match.
- `reminder` is a line given instead of the doc: at a trigger's first match when a package
  already gave the lemon the doc, and on a repeat match 30 or more tool calls after a
  trigger last gave it.

## Packages mode

A `packages` lemon started by `lemonaid lemon start` or `place open` gets its packages
at launch:

- **Claude Code** cuts hook context over 10,000 characters to a preview, so lemonaid
  writes the packages' docs to a file under `<state>/docs/starts/` and passes it as
  `--append-system-prompt-file`. A `--settings` file with `claudeMdExcludes` on
  [`[docs] classic`](config.md#docs) turns off the always-loaded docs. No compaction
  removes a system prompt, so these docs stay through the session, and
  `lemonaid claude resume` passes the same flags again.
- **Codex** gets them from the docs hook at SessionStart, again after `/clear` and after
  each compaction.

A lemon whose packages can't be built starts in `classic`, with a warning.

Each delivery to Claude Code stays under 10,000 characters. When several docs match one
action, the hook gives whole what fits, and for the rest their reminder line, or a line
naming the doc. A doc too long ever to fit is named once, for the lemon to read. Package
docs that don't fit at SessionStart, as in a session started without lemonaid's flags,
arrive over the next tool calls.

A session started without `LEMONAID_DOCS`, such as a fork, gets `[docs] mode`, whatever
its source's mode. For Claude Code that matches what the fork loads: its own launch flags,
not its source's, decide its system prompt.

## Rules for a group or a lead's lemons

A package for `group: oria` reaches every lemon in that group, and a child joins its
parent's groups when it starts. `under: <Lemon-ID>` reaches a lead's whole tree when it
has no group. Classic lemons get these packages and triggers too, since the always-loaded
docs don't carry them; a Claude lemon gets the packages in its system prompt, beside the
always-loaded docs.

A rule written mid-session reaches lemons already running. At each tool call the hook
delivers any doc new to one of the lemon's packages, and the docs of a package the lemon
has newly joined, such as one for a group it was just added to. It rebuilds the index at
most once a minute for this.

## Once per context window

A context window begins when a session starts, is cleared or is compacted, and a resume
continues it. Within a window, a doc or section is given in full once, and again at its next trigger
if the file changes. A package doc changed since it was given is given again when the
next window begins. The state is in `<state>/docs/windows/`.

A subagent's tool calls are not matched: their results go to the subagent's context.

## The log

Each line of `<state>/doc-deliveries.jsonl` has `at`, `harness`, `session`, `window`,
`mode`, `event` and `shadow`.

- A `window` line adds the `source` of its SessionStart, the `cwd` and the `packages` the
  lemon gets. Its `shadow` is true when its mode gives it none of them.
- A `doc` line adds `doc`, `section`, the `package` or `trigger` that brought it,
  `delivery` and `chars`, the length of the text it carries. `delivery` is `full`,
  `reminder`, `refuse` for a `before` trigger's first match, `pointer` for a line naming
  a doc too long to give, or `launch` for a doc in a Claude lemon's system prompt. Its
  `shadow` is true when the lemon's mode only logged it.

## Reading it

```sh
lemonaid docs SESSION       # a session's windows and what each was given
lemonaid docs --self        # the same for the calling lemon
lemonaid docs who DOC       # the live lemons whose current window holds DOC
lemonaid docs table         # every package and every doc with a package or triggers
```

`SESSION` is a session ID, a prefix of one, or a channel. `DOC` is a path or a file name.
`lemonaid docs SESSION` also names any package that is for the lemon now but that its
window didn't get, such as `brief: true` for a lemon given a brief after it started.
`lemonaid docs table` prints Markdown tables, built from the docs under `roots`.

## The hook

`lemonaid hooks install` adds the docs hook on SessionStart, PreToolUse and
UserPromptSubmit in both harnesses, and in Claude Code on PostToolUse after a `Write` that
created a file. A Claude Code Write's result is what says whether it created the file.
The harness waits for each, since each can deliver, and in Codex each has
`"additionalContextLimit": 0`, so a delivery arrives whole. A refusal exits 2 with the
rule on stderr. Without `[docs] roots` they do nothing, and an error delivers nothing.

SessionStart reads every Markdown file's frontmatter under `roots` and caches it by
modification time in `<state>/docs/index.json`, so later starts read only the docs that
changed. Tool calls and prompts match against that cache.
