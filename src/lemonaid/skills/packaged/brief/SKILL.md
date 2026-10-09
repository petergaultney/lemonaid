---
name: brief
description: Update or create your attached lemonaid brief, choose its status, record questions and waiters, check child cleanup, or start a reviewer. Use when asked to update your brief or when work changes what it needs or is waiting on.
---

# Keep your brief current

Your user reads your brief through `lemonaid brief show`, the inbox's `b` key, or tmux's `prefix+b`. Keep `Status:` and `## Now` current so they can tell whose move comes next. Read the whole brief before editing it: its goal, limits, and output still apply.

## Find or create your brief

Run `lemonaid brief show --self`. Your brief is the file attached to your session, normally in `~/.lemons/brief/`. If none is attached but an older `.z/brief*.md` in your place is clearly yours, move it into that folder with a dated name for the work and run `lemonaid brief attach --self <file>`.

If you have no brief, run `lemonaid brief new --self "<what the work is>"`. It creates a dated file and attaches it to you. Give it a task title, `Status: working`, `## Now`, and a short `## Goal` saying what done looks like. Leave out `Parent:` when nobody assigned the work. Keep any generated ID line unchanged.

Name the session for the work, with a short area and change, rather than the brief filename or a personal name: `lemonaid inbox rename --self "<area and change>"`. A launch prompt should name the work first, then point to the brief.

## Choose the status

`Status:` contains exactly one word. The reason goes in `## Now`. Choose by whose move it is:

| Status | When to use it |
|---|---|
| `working` | You are actively doing the work, including fixing conflicts, failed CI, or review findings. |
| `running` | Nothing waits on your user and you are monitoring a named long process. Put the process and its `session:window` under `### Running`. |
| `waiting` | Another lemon, CI, a background run, or a reply comes next. Name it under `### Waiting on`. A lemon reviewer's verdict is `waiting`. |
| `review` | A teammate's approving review on GitHub comes next, rather than your user's or a lemon's. Name the teammate and PR under `### Needs <who>`. |
| `blocked` | Your user can act now: a decision, answer, review, trial, or text to post. Name the move under `### Needs <who>`. Asking your user in your final message counts too. |
| `alert` | Your user's move is needed and harm grows while it waits. Keep this rare; importance alone does not qualify. Say what is getting worse under `### Needs <who>`. |
| `merge` | Only your user's merge remains: reviewer approved, CI green, out of draft, and no conflicts. Check `gh pr view <n> --json mergeable` says `MERGEABLE` every time you set this. |
| `approve` | You reviewed a teammate's PR and recommend your user's approval on GitHub. Name the PR and review doc under `### Needs <who>`. A review of a lemon's PR stays `waiting` on its author or merge. |
| `done` | Your PR merged or closed, or your output was accepted, and no work or waiter remains. |

An open PR is never `done`, and being idle does not make you `done`. Keep watching it until it closes. A reviewer stays `waiting` while a reviewed PR is open, including after approval, because a new push still needs a look.

If your user's move is parked behind something they cannot act on yet, use `waiting`. Name that prerequisite and the move that follows it, then return to `blocked` when they can act. When several lemons wait on the same user move, only the lemon owning the ask uses `blocked` or `merge`; the others wait on it.

Before asking your user to review a PR, check mergeability and green CI too. Conflicts and failed checks are yours to handle. If a `merge` PR gains a conflict, failed CI, or a new finding, return to `working`. Status does not authorize merging; follow your user's review and merge policy.

## Lay out the brief

Keep `## Now` directly after `Status:` and any generated identity fields. Use these sub-headings in this order, omitting empty ones:

1. `### Needs <who>`: a decision, answer, review, merge, or text to post.
2. `### Running`: the process you are monitoring and its `session:window`.
3. `### Waiting on`: the PRs, docs, reviewers, or runs you are watching.
4. `### Next`: what you will do next.
5. `### PRs`: the open PR table below.
6. `### Done`: what finished, always last.

Put a blank line above and below each heading and around its bullets or table. Write for scanning: one item per bullet, opening with its point in a few words. Keep each item to one or two sentences. Do not join separate items with semicolons or inline numbered lists. Put commits, test counts, and paths at the end, or omit them. Replace stale lines instead of appending news, and shrink finished items to one line. Older `- Label:` briefs still work; convert them when you next rewrite `## Now`.

Every open PR you author or review, or that your children author, gets a row under `### PRs`, just before `### Done`:

```markdown
| Work | PR | Review |
|---|---|---|
| A few words on the change | [repo#12](https://github.com/owner/repo/pull/12) | [review doc](https://example.org/reviews/12) |
```

Leave the Review cell empty if no review doc exists. Remove a row once its PR merges or closes.

`## Questions` follows `## Now`. Each question to your user, including an ask in chat, also needs a full entry here so they can answer from the brief alone. Its `###` heading matches the label of its `Needs` bullet (the text before the colon, or the whole bullet if there is no colon). Rewrite the entry when more detail is requested, and remove it once answered. Your overlay may supply the question's prose layout; lemonaid pairs the labels.

The worker owns `Status:`, `## Now`, `## Questions`, and `## Waiters`. The assigning parent owns the task sections from `Parent:` through `## Goal`, `## Context`, `## Limits`, and `## Output`; preserve them. Keep `## Waiters` last, after those sections. The title names the task itself, without a "Brief:" prefix.

## Edit and validate

Prefer the edit verbs. They preserve heading order and spacing, remove empty headings, validate the result, and refuse edits that break the brief:

```sh
lemonaid brief status --self working
lemonaid brief bullet add --self "Next" "open the PR"
lemonaid brief bullet set --self "open the PR" "PR #12 open"
lemonaid brief bullet rm --self "PR #12 open"
lemonaid brief pr add --self <PR-URL> "Delivery service" --review <review-doc-link-or-path>
lemonaid brief pr rm --self 12
```

`bullet set` and `rm` match the beginning of exactly one bullet, ignoring case. `Done` additions go at the top of that section. `lemonaid brief now --self "..."` replaces all of `## Now`; pass `-` to read it from stdin.

In Codex, use the verbs to update a brief outside your workspace. Whether they run without a permission prompt depends on your installed allow rules; hand edits outside the workspace require the applicable filesystem permission. Claude may edit directly. After every hand edit, run `lemonaid brief check --self` and fix its reports. When configured, Claude's Stop hook also checks and prevents the turn ending with an invalid brief; nothing automatically checks a Codex hand edit.

## Record and rearm waiters

With an attached brief, `lemonaid watch doc`, `pr`, `file`, and `briefs` automatically record their restartable command under the final `## Waiters` after startup checks pass. Rearming updates the same entry, including a PR’s head and flags. The saved command keeps the supplied arguments, including `--self`; omitted defaults and temporary state paths are not inserted. No separate `brief waiter add` or `set` is needed for these commands. With `--codex-thread`, recording uses the recipient thread’s attached brief; otherwise it uses the caller’s attached brief.

Use the manual verbs for custom shell waiters and to remove entries when a watch ends permanently:

```sh
lemonaid brief waiter add --self "lemonaid watch pr --wait 12 --repo owner/repo --head abc123 --codex-thread"
lemonaid brief waiter set --self "wait 12" --head def456
lemonaid brief waiter set --self "wait 12" "<replacement command>"
lemonaid brief waiter rm --self "wait 12"
```

`set` and `rm` match a unique substring of the command, ignoring case. `add` is idempotent. Record actual paths, signatures, heads, and harness flags so a restart can rearm the same watches. A listed command is not proof of a running waiter: start it and confirm it started. Rearm after handling each one-shot event, keeping its entry current.

Claude with an attached brief also keeps `lemonaid inbox watch --self` armed as a background Bash task with `timeout: 2147483647`, and records it here. Handle its message and rearm after each exit, including a harness timeout. Codex needs no inbox waiter: lemonaid's delivery service queues messages into the thread.

Idle lemons wait on one-shot events and end the turn; do not self-poll or schedule repeated wakeups. Use the `watch-doc` and `watch-pr` skills for their harness-specific startup and rearm commands.

## Check children and finished work

Run `lemonaid brief children --self` when updating your brief; use `--json` for the tree and `held_by` reasons, or `--all` to include cleaned children. It lists child places, sessions, PRs, status, and descendants such as reviewers.

`cleanup: ready` means the child and its descendants say `done` and none of their sessions has an attached client. It says nothing about whether their code is on the trunk. Verify accepted output and preserved work yourself, then follow your user's cleanup authority and safeguards. Use an explicit place key with `lemonaid place toss <key>`; do not infer permission to force a teardown from `ready`. Preserve briefs as the record.

When your own work is accepted and nothing remains, stop your waiters with `lemonaid watch stop --self`, which also removes their entries (never `pkill -f` a waiter command: it stops every lemon's matching waiter). Remove any entry left for a waiter that had already exited, set `done`, and let your parent clean up your place. Remove closed PR rows from your table.

## Start a reviewer

Use your user's policy for when to review, which harness, window, and review-doc location. The mechanics are:

```sh
lemonaid brief new --child --template review --pr <PR-URL> --review-doc <absolute-doc-path> "Review repo#12: topic"
lemonaid lemon start <your-session>:<review-window> --harness <claude-or-codex> --brief <printed-brief-path> --parent self --name "Review repo#12 topic" --prompt "Review repo#12 topic. Instructions are in <printed-brief-path>; follow them."
```

The first command prints an unattached child brief with you as parent. Add the context the template cannot know: what changed and what needs the hardest check. `lemon start` uses the configured harness command and attaches the brief to the reviewer that starts in that window, not to you. To attach a brief to an already running reviewer, use `lemonaid brief attach --session <session>:<window> <file>`.

The review template keeps findings in the review doc, sets up PR and doc waiters, and keeps the reviewer `waiting` until the PR closes. Fill its head and harness flags before arming those waiters. Keep review findings out of the brief. Follow your user's policy for marking the PR ready after review and CI.
