---
name: brief
description: Update or create your attached lemonaid brief, choose its status, record questions and waiters, check child cleanup, or start a reviewer. Use when asked to update your brief or when work changes what it needs or is waiting on.
---

# Keep your brief current

Your user reads your brief through `lemonaid brief show`, the inbox's `b` key, or tmux's `prefix+b`. Keep `Status:` and `## Now` current so they can tell whose move comes next. Read the whole brief before editing it: its goal, limits, and output still apply.

## Find or create your brief

Run `lemonaid brief show --self`. Your brief is the file attached to your session, normally in `~/.lemons/brief/`. If none is attached but an older `.z/brief*.md` in your place is clearly yours, move it into that folder with a dated name for the work and run `lemonaid brief attach --self <file>`.

If you have no brief, run `lemonaid brief new --self "<what the work is>"`. It creates a dated file and attaches it to you. Give it a task title, `## Now`, and a short `## Goal` saying what done looks like. Leave out `Parent:` when nobody assigned the work. Keep any generated ID line unchanged.

Name the session for the work, with a short area and change, rather than the brief filename or a personal name: `lemonaid inbox rename --self "<area and change>"`. A launch prompt should name the work first, then point to the brief.

## Choose the status

Set `Status:` only when one of the words below applies, and leave it out otherwise. Without one, lemonaid shows your own state: `active` while you are mid-turn, `idle` between turns, and `deaf` or `dead` if a message sent to you would not be read. `lemonaid brief status --self clear` removes a status that no longer applies. Older briefs may say `working` or `waiting`; both read as no status, and setting either clears it.

`Status:` contains exactly one word. The reason goes in `## Now`. Choose by whose move it is:

| Status | When to use it |
|---|---|
| `running` | Nothing waits on your user and you are monitoring a named long process. Put the process and its `session:window` under `### Running`. |
| `review` | A teammate's approving review on GitHub comes next, rather than your user's or a lemon's. Name the teammate and PR under `### Needs <who>`. |
| `blocked` | Your user can act now: a decision, answer, review, trial, or text to post. Name the move under `### Needs <who>`. Asking your user in your final message counts too. |
| `alert` | Your user's move is needed and harm grows while it waits. Keep this rare; importance alone does not qualify. Say what is getting worse under `### Needs <who>`. |
| `merge` | Only your user's merge remains: reviewer approved, no failed CI, out of draft, and no conflicts. Don't wait for CI to go green; your user sees it. Check `gh pr view <n> --json mergeable` says `MERGEABLE` every time you set this. |
| `approve` | You reviewed a teammate's PR and recommend your user's approval on GitHub. Name the PR and review doc under `### Needs <who>`. A review of a lemon's PR sets no status while it waits on its author or merge. |
| `done` | Your PR merged or closed, or your output was accepted, and no work or waiter remains. |

When another lemon, CI, a background run, or a reply comes next, set no status and name it under `### Waiting on`. An open PR is never `done`, and being idle does not make you `done`. Keep watching it until it closes. A reviewer sets no status while a reviewed PR is open, including after approval, because a new push still needs a look.

If your user's move is parked behind something they cannot act on yet, clear your status. Name that prerequisite and the move that follows it under `### Waiting on`, then set `blocked` when they can act. When several lemons wait on the same user move, only the lemon owning the ask uses `blocked` or `merge`; the others wait on it.

Before asking your user to review a PR, check mergeability and that CI hasn't failed. Conflicts and failed checks are yours to handle. If a `merge` PR gains a conflict, failed CI, or a new finding, clear the status while you fix it. Status does not authorize merging; follow your user's review and merge policy.

## Lay out the brief

Keep `## Now` directly after the header. It holds current prose and `### Needs <who>`, `### Running`, and `### Waiting on`. Different people may have separate Needs headings; duplicate heading names are refused without regard to case. `### Lemons` can still list lemons you watch besides your children.

Use this section order, omitting empty sections: header, `## Now`, `## Questions`, `## Next`, `## PRs`, `## Docs`, `## Done`, then the parent's task sections, then `## Watching`. This is a writing convention, not an enforced order. Arbitrary headings are welcome at any level.

`## Next` says what you will do next, `## PRs` holds the open PR table, `## Docs` lists documents for someone to read, and `## Done` records finished work. Readers accept both these sections and the older `###` headings inside Now. Nothing moves automatically. Run `lemonaid brief migrate --self` to promote exactly those four old names, or `--all` for active attached and pending briefs. `brief check` warns about the older layout.

Put a blank line above and below each heading and around its bullets or table. Write for scanning: one item per bullet, opening with its point in a few words. Keep each item to one or two sentences. Do not join separate items with semicolons or inline numbered lists. Put commits, test counts, and paths at the end, or omit them. Replace stale lines instead of appending news, and shrink finished items to one line. Older `- Label:` briefs still work; keep them unless you explicitly migrate the layout.

Every open PR you author or review, or that your children author, gets a row under `## PRs`:

```markdown
| Work | PR | Review |
|---|---|---|
| A few words on the change | [repo#12](https://github.com/owner/repo/pull/12) | [review doc](https://example.org/reviews/12) |
```

Leave the Review cell empty if no review doc exists. Remove a row once its PR merges or closes.

`## Questions` follows `## Now`. Each question to your user, including an ask in chat, also needs a full entry here so they can answer from the brief alone. Its `###` heading matches the label of its `Needs` bullet (the text before the colon, or the whole bullet if there is no colon). Rewrite the entry when more detail is requested, and remove it once answered. Your overlay may supply the question's prose layout; lemonaid pairs the labels.

The worker owns `Status:`, `## Now`, `## Questions`, `## Next`, `## PRs`, `## Docs`, `## Done`, `## Executive Summary of Results`, and `## Watching`. In the Markdown brief, put `## Executive Summary of Results` just after `## Goal`; `brief show` renders a populated summary first, before Needs and the rest of the body. The assigning parent owns the task sections from `Parent:` through `## Goal`, `## Context`, `## Acceptance Criteria`, and `## Limits`; preserve them. Keep `## Watching` last, after those sections. The title names the task itself, without a "Brief:" prefix.

Before setting `Status: done`, fill `## Executive Summary of Results` with a concise account of the outcome: at most 1–3 paragraphs, plus any absolutely critical table. This summary belongs in the brief even when the full output lives elsewhere. For a review brief, put the verdict here. `brief check` warns if a done brief has this heading but leaves it empty; it does not block the status edit, and older briefs without the heading remain valid.

## Edit and validate

Prefer the edit verbs. They preserve existing heading order and spacing, remove emptied headings, validate the result, and refuse edits that break the brief:

```sh
lemonaid brief status --self blocked
lemonaid brief status --self clear
lemonaid brief bullet add --self "Next" "open the PR"
lemonaid brief bullet set --self "open the PR" "PR #12 open"
lemonaid brief bullet rm --self "PR #12 open"
lemonaid brief pr add --self <PR-URL> "Delivery service" --review <review-doc-link-or-path>
lemonaid brief pr rm --self 12
lemonaid brief section show --self "Notes"
lemonaid brief section set --self "Notes" -          # body from stdin; new headings default to ##
lemonaid brief section set --self "Detail" --level 3 --parent "Notes" -
lemonaid brief section rm --self "Detail"             # removes its descendants too
lemonaid brief migrate --self
```

`bullet add` accepts any heading name. Existing headings retain their level; missing headings default to level 2, except Needs, Running, Waiting on, and Lemons, which are created under Now.

`bullet set` and `rm` match the beginning of exactly one direct bullet anywhere in the brief, ignoring case; `--heading "Notes"` scopes the match. Fenced examples are ignored. Duplicate heading names are refused with their parent and line number, rather than choosing one.

`Done` additions go at the top of that section.

`lemonaid brief now --self "..."` replaces progress in `## Now`, keeping existing PRs and Docs tables when their headings are omitted; pass `-` to read it from stdin. It refuses a body that drops any other sub-heading the section has; to change one line use the bullet verbs, and to rewrite the whole section pass `--replace-all` (

`lemonaid brief now --self --replace-all -`). Supplying a legacy PRs or Docs heading replaces that table. Once promoted sections exist, `brief now` still edits Now in place and leaves the separate sections unchanged. Its replacement body must omit Next, PRs, Docs and Done headings, including with `--replace-all`; edit a separate section with `lemonaid brief section set --self "Next" -` (substitute its heading), or use the bullet verbs. `brief now` never migrates headings. Use `brief pr rm` or `brief doc rm` to remove individual rows.

<!-- harness: claude -->
You may edit a brief directly. After every hand edit, run `lemonaid brief check --self` and fix its reports; the Stop hook also keeps the turn from ending with an invalid brief.
<!-- /harness -->

<!-- harness: codex -->
Use the verbs to update a brief outside your workspace. Whether they run without a permission prompt depends on your installed allow rules; hand edits outside the workspace require the applicable filesystem permission. After every hand edit, run `lemonaid brief check --self` and fix its reports; nothing automatically checks a Codex hand edit.
<!-- /harness -->

## Declare subscriptions and watch them

`## Watching` lists one `lemonaid watch` command per line; legacy `## Waiters` remains readable. Edit it with `brief watching add|set|rm` (`brief waiter` is an alias). These lines describe subscriptions, regardless of whether a separate waiter is running.

List every doc you wrote for someone to read with `lemonaid brief doc add --self <path> "<purpose>"`; `--watch "All edits"` also watches its body. The Watch column accepts `Relay comments` (the default) or `All edits`, not booleans. `brief doc rm` removes the row. `Output-Doc:` supplies the first row, starting `watch doc` adds one, and `brief check` warns about linked documents without rows.

List a lemon you must hear about, a child or not, with `lemonaid brief lemon add --self <lemon-id-channel-or-brief> --purpose "<why>"`; repeat `--to STATUS` (or `needs`) to choose what wakes you, default `merge`, `done` and `needs`. `brief lemon set` changes a row and `brief lemon rm` removes it. An explicit row for a child replaces its defaults. Every watched lemon is also reported once when its harness exits, its session or place is gone, or it is deaf, unless its brief is `done`.

Read your work's current state first. `lemonaid watch --self` reads Watching, PRs (with comments and CI), Docs, Lemons rows, your inbox and your children's statuses and liveness, and reports all pending sources in one batch. A first subscription takes current state as seen, except unanswered doc threads. Document subscriptions continue while your session exists, whatever its Status.

<!-- harness: claude -->
Check `lemonaid watch --self --status`. If it says `push scout running`, lemonaid is watching for you and pushes each batch into your session; handle each batch as it arrives. If it says `no watcher running`, run `lemonaid watch --self --push`, which starts a detached scout and returns. Only if that prints `not started`, run `lemonaid watch --self` as a background Bash task (`run_in_background`, `timeout: 2147483647`) and rearm it after handling each batch. Stop separate inbox, PR and children waiters before switching.
<!-- /harness -->

<!-- harness: codex -->
Check `lemonaid watch --self --status`. If it says `push scout running`, lemonaid is watching for you and queues each batch into your thread; handle each batch as it arrives. If it says `no watcher running`, run `lemonaid watch --self --push` with escalated permissions, which starts the scout and returns; only if that prints `not started`, run `lemonaid watch --self --codex-thread` in an escalated exec_command session and rearm it after each batch. Stop separate inbox, PR and children waiters before switching. An idle Codex without an armed waiter may not start a turn for queued messages; `tell` treats it as deaf and prompts it to read its inbox.
<!-- /harness -->

Idle lemons wait on events and never self-poll or schedule repeated wakeups.

## Check children and finished work

The unified watcher watches child status changes automatically. Add an explicit `watch briefs --children --self --to <status>` subscription to select destination statuses.

A lead may add a `Name words:` line to its brief header: five- and three-letter words tied to its work, best first (`Name words: audit check ink web`). Its children are named from them (`AuditInk`); `--name-words` on `brief new --child` overrides the line for one child.

Run `lemonaid brief children --self` when updating your brief; use `--json` for the tree and `held_by` reasons, or `--all` to include cleaned children. It lists child places, sessions, PRs, status, and descendants such as reviewers.

`cleanup: ready` means the child and its descendants say `done` and none of their sessions has an attached client. It says nothing about whether their code is on the trunk. Verify accepted output and preserved work yourself, then follow your user's cleanup authority and safeguards. Use an explicit place key with `lemonaid place toss <key>`; do not infer permission to force a teardown from `ready`. Preserve briefs as the record.

When your own work is accepted and nothing remains, stop your waiters with `lemonaid watch stop --self`, which also removes their entries (never `pkill -f` a waiter command: it stops every lemon's matching waiter). Remove any entry left for a waiter that had already exited, set `done`, and let your parent clean up your place. Remove closed PR rows from your table.

## Start a reviewer

The packaged review template sets `Hidden: yes`, so no separate `brief hide` command is needed. Use `brief hide` for other lemons you want out of the default inbox.

Use your user's policy for when to review, which harness, window, and review-doc location. The mechanics are:

```sh
lemonaid brief new --child --template review --pr <PR-URL> --output-doc <absolute-doc-path> "Review repo#12: topic"
lemonaid lemon start <your-session>:<review-window> --harness <claude-or-codex> --brief <printed-brief-path> --parent parent --name "Review repo#12 topic" --prompt "Review repo#12 topic. Instructions are in <printed-brief-path>; follow them."
```

The first command prints an unattached child brief with you as parent; `--parent parent` then starts the reviewer as your sibling, a child of your own parent, and tells that parent in its inbox. With no parent of your own, the reviewer has none either. Use `--parent self` only for a reviewer that should report to you. Add the context the template cannot know: what changed and what needs the hardest check. `lemon start` uses the configured harness command and attaches the brief to the reviewer that starts in that window, not to you. To attach a brief to an already running reviewer, use `lemonaid brief attach --session <session>:<window> <file>`.

The review template keeps findings in the review doc, sets up PR and doc waiters, and keeps the reviewer watching, with no status, until the PR closes. Read the PR and arm `watch --self` for the subscriptions it lists. Keep review findings out of the brief. Follow your user's policy for marking the PR ready after review and CI.
