# Groups

A group is a name for a set of lemons, so many efforts stay findable in the inbox. A lemon can be in any number of groups. Parent links can seed a group, but don't define one: a reviewer is parented by the lemon whose PR it reviews, and a control center may parent everything.

```bash
lemonaid group create "Inbox work" self --tree       # me, my children, their children
lemonaid group add "Inbox work" <lemon> [<lemon>...]   # --tree adds each one's descendants
lemonaid group remove "Inbox work" <lemon>
lemonaid group rename "Inbox work" "Inbox"
lemonaid group delete "Inbox"                          # the lemons themselves are untouched
lemonaid group color "Inbox" teal                     # or #rrggbb; --clear forgets it
lemonaid group list [--self | --lemon <lemon>]         # every group, or one lemon's
lemonaid group move "Inbox" --up                       # or --down, or --to 2 (one-based)
lemonaid group sync <lemon>                            # set its groups from its brief's line
lemonaid place open feat/x --brief <file> --parent self --group "Inbox work"
lemonaid lemon start work:4 --brief <file> --group "Inbox work"
```

A `<lemon>` is a Lemon-ID, an attached lemon's channel, a brief's name or path, or `self`, as for `lemon parent`. The brief need not be attached yet, so a lead can put a child in its group before the child starts. Every command takes `--json`.

- **`create` makes a group; `add` needs one that exists,** so a mistyped name is an error rather than a second group. So does `--group` on `place open` and `lemon start`, which checks before anything opens.
- **A group with no members is gone,** as far as anything shows: `list`, the inbox and its `+` list leave it out, and there's nothing to clean up. Making a group with its name again brings it back, in its old place, and renaming another group to that name takes it over.
- **Names are trimmed, unique, and can't contain a comma** or a control character.
- **A child joins its parent's groups:** when `brief new --child` writes its brief, and when `place open` or `lemon start` starts it with `--parent` and no `--group`. `--group` names other groups instead. A resumed or replacement session on the same brief keeps its groups, since they belong to the brief's Lemon-ID. Starting it again with `--parent` adds the parent's groups back, even ones it was removed from. A lead finds its own groups with `group list --self`.

## Where groups live

The inbox database holds groups and their members, keyed on Lemon-ID (the brief's `Brief-ID:`), so membership survives resumes, renamed briefs and rerolled IDs. The inbox reads only the database.

Each member brief also carries a `Groups:` line in its header, after `Status:`, `Parent:` and `Area:`, naming its groups:

```markdown
Status: blocked
Parent: lead.TinCup (lead), 2026-10-09
Groups: Inbox work, Relay
```

The line is how groups travel with a brief to another machine:

- **Every group change rewrites the line** in each affected brief: `create`, `add`, `remove`, `rename`, `delete` and `--group`. A brief that couldn't be written is reported (`unwritten` in `--json`).
- **A Brief-ID new to this database brings its line in.** The first command that needs the brief's Lemon-ID (an `--self` command from its lemon, `tell`, `place open --brief`, ...) registers it, and registering it reads the line, creating any group that doesn't exist here yet.
- **After that the database wins.** `brief check` reports a line that disagrees with it, so a Claude lemon's Stop hook catches a hand edit that dropped the line. `group sync` goes the other way, setting a lemon's groups from its line; a brief with no line is left as it was.
- **Order, collapse and saved color belong to one machine,** like pins: they're how one person reads their inbox, not part of the work.

Two machines both working on one brief at once would each rewrite its line from their own database. That isn't supported.

## In the inbox

`lma` draws each group under a header line naming it and its visible/member count (`▾ Inbox work (1/3)`). The total counts group members with current inbox sessions, including those hidden by reviewer filtering or folding. Archived, snoozed, and historical members without an inbox session do not count. When every member is visible, the count reads simply `(3)`:

- **Order:** pinned lemons in no group come first, then the remaining lemons in no group in their usual status order, then groups in the order you set. Set `[inbox] ungrouped_first = false` to put ungrouped lemons below groups. Lemons inside each group keep their usual status order, with visible parents promoted before their children in that group. Siblings keep their relative order. Pins and deaf rows keep their leading positions, and a usable arranger answer takes precedence over parent ordering. Opening the fold restores both grouped and ungrouped lemons in their order. Focusing a lemon keeps it visible without moving it ahead of folded members of its group or ungrouped block.
- **A parent's dim `↓N` counts all its active direct children, across groups.** Hidden and folded children count; archived and snoozed sessions do not. If only some children are drawn, `↓2/5` means two visible out of five active. A child drawn in several groups counts once. The marker stays immediately left of the emoji in the persistent indicator strip; column rows reserve a slot so names stay aligned.
- **Moving the cursor marks the highlighted lemon's family:** a bright `↑` on its visible direct children points toward their parent, and `↓` on its visible parent points toward its child. These marks follow the highlight without activating a session, including across groups and the other-terminals list. Hidden rows stay hidden; a group header or unrelated row clears the marks. The `?` help explains the bright relationship arrows and dim child counts.
- **A pinned lemon in a group heads that group,** and stays visible when the group is collapsed. Pin a lead to keep it in sight with its group out of the way.
- **A group's lead sorts first among the group's rows,** an extension of parents before children. The lead is the member with the most descendants among the group's members that have inbox sessions: children, grandchildren and so on, with lemons outside the group allowed along the way. Ties go to the member that comes first in the group. It sorts above every pinned lemon in the group. It is only an ordering: nothing is pinned, collapsing hides the lead like any member, and the header's count and color are unchanged. Edge cases:
  - A member with no descendants in the group leads nothing, so a group with no lineage, or one member, has no lead.
  - Members with other parents don't unseat the lead; only a change in the lineage does.
  - A drawn member pulls its ancestors in that group into view, so a parent folded by status, or hidden as a brief, still shows while a child is drawn, whether or not a fold is configured. A collapsed group still hides everyone, and ancestors of members that are folded away stay folded.
  - Only members with inbox sessions count: archived, snoozed and historical members are ignored, and a hidden or folded member that has a session still counts.
  - Leadership is per group: a lemon in two groups leads one and not the other.
  - Group order and the ungrouped lemons are untouched.
  - A `♛` in the indicator strip, beside the emoji and before the child count, marks the lead; it is shown only on the lead's row under that group, and is a different mark from the pin's `▪` and the `↑`/`↓` arrows.
  - Set `[tui] group_lead_first = false` to turn off the sort, the `♛` and the ancestor rule.
- **A lemon in two groups appears in both.**
- **`Enter` on a header collapses the group,** leaving only the header and any rows that remain visible; a collapsed group with no visible rows reads `(0/3)` for three current members. Pinned lemons remain visible, and `Tab` also collapses or opens a group from its header or any of its lemons. A lemon you collapse from stays drawn under the cursor until you move off it. A collapsed header (`▸`) is filled with the color of its most pressing row: `alert` red, `blocked` yellow, and so on in the band order of `docs/arrange.md`. Being unread doesn't fill a header: a group with an unread row shows a dot after its count. Nor does `done`, so a pinned lemon under the header never looks done because another lemon in its group is.
- **`Shift`+`↑` / `Shift`+`↓` on a header move the group up or down** in the persistent group order, across status bands. The same order is used by `lemonaid group list`; `lemonaid group move <name> --up`, `--down` or `--to N` changes it from a script.
- **Each header is underlined across the list's width,** so stacked collapsed headers of one color stay apart.
- **A group's color comes from the palette by name,** moved off any look-alike among the current groups, so two groups don't share a hue. `group color` or `C` in the inbox saves one, drawn at once, and `[tui.group_colors]` in the config sets one by name; a saved color wins over the config. See [Group colors](config.md#group-colors).
- **The header's arrow, count and underline take the group's color,** like its name; only the unread dot and a status fill's text keep theirs. Under the cursor the arrow becomes a block of that color, and in the sidebar a white block marks the right edge, since the table's cursor color doesn't show through a status fill.
- **In the sidebar, a group's cards sit one column in, behind a rail** (`▌`) in the group's color that runs continuously between cards and stops before the last card's separator. The separator keeps the normal background even when the card is selected. Cards in no group keep the full width. The current lemon's card has a three-sided frame, with its left edge just inside the group's rail and its bottom edge in the separator line. Every card keeps the right edge free, so marking one leaves its text in place. It's near white on a dark theme and near black on a light one, which no group's color is.
- **A group with a current lemon is always drawn,** even when none of its lemons shows: all folded, hidden, or filtered out. Its header then reads `(0/3)`, and it can still be moved, collapsed or recolored there. A group with no current lemon (no members, or all of them snoozed or archived) isn't drawn, and comes back when one of its lemons does. The grove draws a block only for a group that is some lemon's first group, so a group can have a header in the inbox and no block in the grove, never the reverse.
- **Row keys skip headers.** Number keys count lemons only, the brief view's up and down step over headers, and actions on a header (mark read, archive, ...) do nothing.
- **Folding:** a row that `[tui] fold_statuses` or an arranger's `folded` list folds is hidden in place inside its group, and the fold key shows it there again. The header's count then reads `(2/3)`: two visible rows, three current members. Opening the fold counts the newly visible rows too. A group whose rows are all folded keeps only its header, `(0/3)`, and its rows come back when the fold opens. The fold line counts folded rows in groups too: `▸ idle (5) · w to show`.
- **Search** shows matches as a flat list, without groups.

Collapse, order and saved colors are stored in this machine's database and survive restarts. Group order is independent of member status and unread state.

## Editing in the inbox

| Key | On a lemon | On a group's header |
|-----|------------|---------------------|
| `G` | Put the lemon, its children and their children in a group you name, new or existing | - |
| `+` | Put the lemon in a group: pick one, or type a new name | - |
| `-` | Take the lemon out of the group it's drawn under | Delete the group |
| `r` | Rename the session | Rename the group |
| `C` | Save a color for the group it's drawn under | Save a color for the group |
| `Z` | Undo the last change, a group edit included | |

- **`G` asks for the group's name first,** offering the lemon's session name, with commas made spaces. Enter puts the lemon and its tree in the group of that name, making it if there's none; a name already taken means that group, never a near copy of it. Escape changes nothing.
- **`+` lists the groups with members that the lemon isn't in.** Typing narrows the list, and a name no group has adds `New group: <name>` at the bottom. Enter takes the highlighted line. Naming a group the lemon is already in says so and changes nothing.
- **The cursor stays on the lemon** wherever an edit moves it: into a group, out of one, or into a collapsed group, where it stays drawn until the cursor leaves it.
- **`C` asks for a color,** offering the saved one: `#rrggbb`, `#rgb`, `rgb(r, g, b)` or a CSS name such as `teal`. Enter saves it and the group is redrawn in it; an empty box clears the saved color, so the config's or the automatic one applies again.
- **`-` acts at once, without asking,** and says what it did. A lemon in two groups is drawn under each, so the row you're on says which group it leaves. Deleting a group leaves its lemons as they were.
- **`Z` undoes each of these,** a deleted group coming back with its name, place, collapse, saved color and members. It refuses, changing nothing, once the group has changed since, by another inbox edit or `lemonaid group`, and drops that edit from the undo list. When the group's old name has been taken, it keeps the edit, so `Z` works again once the name is free.
- **Each edit rewrites the `Groups:` line** of the briefs it touches, as the CLI does. A brief it couldn't write is named in a warning.
- **A lemon needs a brief to be in a group,** since membership is kept by Lemon-ID; the keys say so on a session without one. They do nothing in the brief view, history or the snoozed list.

The keys are `group_tree`, `group_add`, `group_remove` and `group_color` in `[tui.keybindings]` (see [keybindings.md](keybindings.md)).
