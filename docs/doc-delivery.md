# Doc delivery

A lemon needs a rule when it is about to do the thing the rule governs, not only when its
session starts. Lemonaid lets each doc say, in its own frontmatter, which lemons get it at
session start and which actions bring it back. The docs live under the folders
[`[docs] roots`](config.md#docs) lists.

**Delivery is in shadow mode.** `lemonaid hooks docs` works out what each lemon would be
given and logs it to `doc-deliveries.jsonl`, but gives it nothing. Use the log to check
that packages and triggers fit before they deliver.

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
  after the call has run, so its first match in each context window will refuse the call,
  with the section as the reason, even when a package already gave the lemon the doc.
- `reminder` is a line given instead of the doc: at a trigger's first match when a package
  already gave the lemon the doc, and on a repeat match 30 or more tool calls after a
  trigger last gave it.

## Once per context window

A context window begins when a session starts, is cleared or is compacted, and a resume
continues it. Within a window, a doc or section is given in full once, and again only if
the file changes. The state is in `<state>/docs/windows/`.

A subagent's tool calls are not matched: their results go to the subagent's context.

## The log

Each line of `<state>/doc-deliveries.jsonl` has `at`, `harness`, `session`, `window`,
`mode`, `event` and `shadow`.

- A `window` line adds the `source` of its SessionStart, the `cwd` and the `packages` the
  lemon gets.
- A `doc` line adds `doc`, `section`, the `package` or `trigger` that brought it,
  `delivery` (`full`, `reminder`, or `refuse` for a `before` trigger's first match) and
  `chars`, the length of the text it carries.

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
Since they deliver nothing, the harness waits only for the SessionStart one, which begins
the context window before the session's first prompt or tool call is matched. Without
`[docs] roots` they do nothing.

SessionStart reads every Markdown file's frontmatter under `roots` and caches it by
modification time in `<state>/docs/index.json`, so later starts read only the docs that
changed. Tool calls and prompts match against that cache.
