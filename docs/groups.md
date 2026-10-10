# Groups

A group is a name for a set of lemons, so many efforts stay findable in the inbox. A lemon can be in any number of groups. Parent links can seed a group, but don't define one: a reviewer is parented by the lemon whose PR it reviews, and a control center may parent everything.

```bash
lemonaid group create "Inbox work" self --tree       # me, my children, their children
lemonaid group add "Inbox work" <lemon> [<lemon>...]   # --tree adds each one's descendants
lemonaid group remove "Inbox work" <lemon>
lemonaid group rename "Inbox work" "Inbox"
lemonaid group delete "Inbox"                          # the lemons themselves are untouched
lemonaid group list [--self | --lemon <lemon>]         # every group, or one lemon's
lemonaid group sync <lemon>                            # set its groups from its brief's line
lemonaid place open feat/x --brief <file> --parent self --group "Inbox work"
lemonaid lemon start work:4 --brief <file> --group "Inbox work"
```

A `<lemon>` is a Lemon-ID, an attached lemon's channel, a brief's name or path, or `self`, as for `lemon parent`. The brief need not be attached yet, so a lead can put a child in its group before the child starts. Every command takes `--json`.

- **`create` makes a group; `add` needs one that exists,** so a mistyped name is an error rather than a second group. So does `--group` on `place open` and `lemon start`, which checks before anything opens.
- **Names are trimmed, unique, and can't contain a comma** or a control character.
- **A child joins its parent's groups:** when `brief new --child` writes its brief, and when `place open` or `lemon start` starts it with `--parent` and no `--group`. `--group` names other groups instead. A resumed or replacement session on the same brief keeps its groups, since they belong to the brief's Lemon-ID. Starting it again with `--parent` adds the parent's groups back, even ones it was removed from. A lead finds its own groups with `group list --self`.

## Where groups live

The inbox database holds groups and their members, keyed on Lemon-ID (the brief's `Brief-ID:`), so membership survives resumes, renamed briefs and rerolled IDs. The inbox reads only the database.

Each member brief also carries a `Groups:` line in its header, after `Status:`, `Parent:` and `Area:`, naming its groups:

```markdown
Status: working
Parent: lead.TinCup (lead), 2026-10-09
Groups: Inbox work, Relay
```

The line is how groups travel with a brief to another machine:

- **Every group change rewrites the line** in each affected brief: `create`, `add`, `remove`, `rename`, `delete` and `--group`. A brief that couldn't be written is reported (`unwritten` in `--json`).
- **A Brief-ID new to this database brings its line in.** The first command that needs the brief's Lemon-ID (an `--self` command from its lemon, `tell`, `place open --brief`, ...) registers it, and registering it reads the line, creating any group that doesn't exist here yet.
- **After that the database wins.** `brief check` reports a line that disagrees with it, so a Claude lemon's Stop hook catches a hand edit that dropped the line. `group sync` goes the other way, setting a lemon's groups from its line; a brief with no line is left as it was.
- **Order and collapse belong to one machine,** like pins: they're how one person reads their inbox, not part of the work.

Two machines both working on one brief at once would each rewrite its line from their own database. That isn't supported.

## In the inbox

`lma` draws each group under a header line naming it and how many of its lemons have rows (`▾ Inbox work (3)`):

- **Order:** pinned lemons in no group come first. Each group then sits among the other rows by its most pressing row's status, above single lemons of the same status: a group holding a `blocked` lemon heads the `blocked` rows. Groups in the same band keep their own order, and an empty group goes last.
- **A pinned lemon in a group heads that group,** and stays visible when the group is collapsed. Pin a lead to keep it in sight with its group out of the way.
- **A lemon in two groups appears in both.**
- **`Enter` on a header collapses the group,** leaving only the header, and opens it again. `Tab` does the same from the header or any of the group's lemons; a lemon you collapse from stays drawn under the cursor until you move off it. A collapsed header (`▸`) is filled with the colour of its most pressing row: `alert` red, `blocked` yellow, and so on in the band order of `docs/arrange.md`. Being unread doesn't fill a header: a group with an unread row shows a dot after its count.
- **`Shift`+`↑` / `Shift`+`↓` on a header swap the group with the next header up or down,** the keys that move a pin. They only reorder groups in the same band; past a group in another band they say so and do nothing.
- **Each header is underlined across the list's width,** so stacked collapsed headers of one colour stay apart.
- **A group's colour comes from the palette by name,** moved off any look-alike among the current groups, so two groups don't share a hue. `[tui.group_colors]` in the config sets one by name; see [Group colors](config.md#group-colors).
- **The header's arrow, count and underline take the group's colour,** like its name; only the unread dot and a status fill's text keep theirs. Under the cursor the arrow becomes a block of that colour, and in the sidebar a white block marks the right edge, since the table's cursor colour doesn't show through a status fill.
- **In the sidebar, a group's cards sit one column in, behind a rail** (`▌`) in the group's colour that runs unbroken down every line. Where the rail stops, the group ends. Cards in no group keep the full width.
- **A group is never hidden.** One whose lemons have no rows shows its header alone, with `(0)`.
- **Row keys skip headers.** Number keys count lemons only, the brief view's up and down step over headers, and actions on a header (mark read, archive, ...) do nothing.
- **Folding:** a row that `[tui] fold_statuses` or an arranger's `folded` list folds is hidden in place inside its group, and the fold key shows it there again. The header's count then reads `(2/3)`: two rows not folded, three in all.
- **Search** shows matches as a flat list, without groups.

Collapse and order are stored in this machine's database and survive restarts.

## Editing in the inbox (coming next)

- **One key makes a group** of the selected lemon, its children and their children, named after the lemon's session, and lets you rename it there.
- **Keys to add or remove** the selected lemon, and to rename or delete the group under the cursor.
