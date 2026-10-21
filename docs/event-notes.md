# Event notes

An event note is your own text, added to a watcher event of one kind whenever a lemon
receives it. Use one to remind a lemon of your policy at the moment it applies. For
example, when a child goes `done`, tell its parent that cleaning up the child is its job.

Write one Markdown file per kind in `~/.lemons/event-notes/`, named for the kind:

```text
~/.lemons/event-notes/
  child.done.md
  child.needs.md
```

```markdown
If you agree its work is complete, cleaning up its place is your job (normally
`lemonaid place toss <key> -y`; see your brief skill). Decide in this turn.
```

A child going `done` then reaches its parent like this:

```text
fix-auth.AceJot: Status: merge -> done (/Users/me/.lemons/brief/2026-10-21-fix-auth.md)
Your notes for these events:
- child.done: If you agree its work is complete, cleaning up its place is your job (normally
  `lemonaid place toss <key> -y`; see your brief skill). Decide in this turn.
```

- **Notes add to an event; they never replace it.** Lemonaid's own text, and any guidance
  it carries, comes first and keeps following upgrades.
- **One note per kind per report.** Three children going `done` together carry the
  `child.done` note once.
- **Edits apply on the next delivery.** The directory is read each time an event with
  notes is delivered, so a running watcher needs no restart.
- **Harness sections work as in a skill overlay.** Lines between
  `<!-- harness: claude -->` (or `codex`) and `<!-- /harness -->` reach only that harness
  ([Skills](skills.md#text-for-one-harness)).
- **A note is capped at 2000 characters** and cut beyond that. A file that can't be read,
  or whose name isn't a kind, is skipped and logged. It never stops a delivery.

Notes are instructions every matching lemon receives, like your CLAUDE.md. Lemons can write
to `~/.lemons/`, so a lemon should edit a note only when you ask it to.

## Kinds

`lemonaid watch notes list` prints every kind and stars the ones with a note.
`--json` gives the same as data, with any problems found in the directory, and the command
exits 1 when there are problems. `lemonaid watch notes show <kind> [--harness codex]`
prints a note as a lemon would receive it.

Each kind is `<origin>.<event>`. The origin is how the lemon receiving the event is
connected to the lemon it describes:

| Origin | The described lemon is |
|---|---|
| `child` | its child, by parent link |
| `watched` | listed in its `### Lemons` table, and not its child |
| `orphan` | a brief no live lemon owns, from `watch briefs --orphans` |

The event is one of:

| Event | When |
|---|---|
| `running`, `done`, `blocked`, `merge`, `approve`, `alert`, `review` | its Status became that word, and that status wakes the watcher |
| `none` | its Status was cleared, where that wakes the watcher |
| `needs` | it has a new or changed Needs ask, where Needs asks wake the watcher |
| `exited` | its harness exited |
| `gone` | its tmux session, directory or brief attachment is gone |
| `deaf` | a message sent to it would not be read |

So `child.done` is for a parent whose child goes `done`, and `orphan.done` is for the lemon
watching orphans. A note never changes which events wake a lemon. A note for `child.blocked`
appears only if the parent's watcher wakes on `blocked`.

Other watcher events (PRs, documents, repos, files and inbox messages) don't carry notes yet.
