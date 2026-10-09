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

## In the inbox (coming next)

Groups are drawn as sections of the list, each under a header line with its name:

- **Order:** pinned rows first, then each group in its order, then the lemons in no group. Groups are reordered with a key, and keep their order across restarts.
- **A lemon in two groups appears in both.** A pinned lemon appears only among the pins.
- **Within a group,** rows keep the order lemonaid or the arranger gives them. The arranger's snapshot gains each row's groups, and its `folded` list folds only rows in no group: a group that's in the way is collapsed instead.
- **A group is never hidden.** Collapsing one leaves its header, which shows how many lemons it has and takes the highlight of its most important status, in the band order of `docs/arrange.md` (`alert` first). A group whose lemons have no rows shows its header alone.

## Editing in the inbox (after that)

- **One key makes a group** of the selected lemon, its children and their children, named after the lemon's session, and lets you rename it there.
- **Keys to add or remove** the selected lemon, and to rename or delete the group under the cursor.
