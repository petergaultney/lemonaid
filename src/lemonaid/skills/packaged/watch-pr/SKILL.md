---
name: watch-pr
description: Wait, at zero token cost, until a GitHub PR gets a new push, is merged/closed, is marked ready for review or back to draft, changes review decision, or (with --comments) gets a new comment from someone else, conflicts with its base, or fails CI, or with --ci finishes CI passing or failing, then wake and act on it. Use on every PR you open (with --comments), and when waiting on someone to update a PR you've reviewed or are watching.
---

# Watch a PR for pushes, state changes, review comments, and CI

## Arguments

A PR number or URL. If omitted, infer it from the current branch (`gh pr view --json number`).

- `--comments --me "<your signature>"`: also wake on new comments from anyone but you, and, as the PR's author, when it starts conflicting with its base or its CI fails. Use it on every PR you open. `<your signature>` is the one you sign Relay Comments with, e.g. `Author (MotorHoe)`.
- `--ci`: also wake when CI finishes on the current head, passing or failing. Combines with `--comments`, `--once`, and `--codex-thread`; it does not require `--comments`.
- `--legacy <name>`: another signature whose comments count as yours, e.g. one you signed with before (repeatable).
- Without `--comments` or `--ci`: pushes, merge/close, draft/ready, and review decision only, e.g. when you reviewed someone else's PR. Conflicts and CI are the author's to fix, so a reviewer isn't woken for them.

A comment counts when it is in any review thread, including outdated and resolved threads, a submitted review's body, or the PR conversation. Lemons usually post with their human's GitHub account, so sign everything you post right after the marker: `🍋 Author (MotorHoe): ...`. A comment is skipped as yours only when it starts with 🍋, then your `--me` or a `--legacy` signature, then a colon. Every other comment wakes you, including other lemons' 🍋 comments, signed or not. Bots and pending (unsubmitted) review comments never count. Comments already reported to `--me` are remembered, so a rearm doesn't wake you on one you handled.

For quieter waits, use `--skip-outdated` and/or `--skip-resolved`, or set `skip_outdated = true` and/or `skip_resolved = true` under `[watch.pr]` in the lemonaid config. Both default to false. `--no-skip-outdated` and `--no-skip-resolved` override configured filters for one wait. These filters apply only to review threads.

## Waiters in your brief

With an attached brief, the watch command automatically records its restartable command under the final `## Waiters` after startup checks pass. The command keeps the supplied arguments without injecting defaults or temporary state paths. Rearming updates the same entry, including the head and flags; you do not need a separate `brief waiter add` or `set`. Confirm it is running with `--status`: a saved command can remain while a one-shot waiter has exited.

Keep the entry across one-shot events while you handle them and rearm. When the watch ends permanently, remove it with `lemonaid brief waiter rm --self "<unique command substring>"`. Without an attached brief, the command watches normally without recording. With `--codex-thread`, recording uses the recipient thread’s attached brief; otherwise it uses the caller’s attached brief.

## Choosing where to test

Use local tests during active development when their feedback helps you make the next change. After a small tweak whose behavior you understand, you may choose to push and let CI validate it instead of running the suite locally and then waiting for the same checks again. Use your judgment about the change and the CI coverage.

When relying on CI, add `--ci` to your next waiter alongside `--comments` and keep it on each rearm until CI finishes on the head you need validated. A push or comment can wake you before CI completes; handle that event and rearm with `--ci` still present. Once you handle the CI result, rearm without `--ci` for the usual comment and failure watch.

CI completion waits for every check on the current head to finish. Required checks determine the result when any are present; otherwise all checks count. No checks is not a completion. A completion is remembered once per head and watcher identity, so rearming with `--head` does not repeat it, even when switching between `--comments` and `--ci`.

## Waiting

Check for an existing waiter first: `lemonaid watch pr --status <number> [--me "<your signature>"]`, with the same `--me` as the waiter. If one is running, don't start another; a second one for the same PR and name refuses to start.

In Claude Code, start the waiter with `--once` as a background Bash task, then end your turn:

```
Bash(
  command: lemonaid watch pr --wait <number> --head <current head sha> --once [--comments --me "<your signature>"],
  description: "Wait for pushes / state / comments on PR #<number>",
  run_in_background: true,
  timeout: 2147483647,
)
```

It prints the first event and exits, and the task's completion wakes you. Handle the event, then rearm the same way with `--head` set to the head you just handled.

- Don't use `Monitor`: it expires after 30 minutes and wakes you for nothing.
- Don't run the waiter without `--once` in background Bash: its output goes to a file and never wakes you.
- Pass `timeout: 2147483647`. Claude Code stops a background task after 30 minutes by default, and after its `BASH_MAX_TIMEOUT_MS` ceiling otherwise. If the harness stops the waiter anyway, rearm it, whatever the notice says.

In Codex, check that `CODEX_THREAD_ID` is set and `codex queue --help` succeeds, then start `lemonaid watch pr --wait <number> --repo <owner/name> --head <current head sha> [--comments --me "<your signature>"] --codex-thread` (bare: it reads `CODEX_THREAD_ID` itself; never write `"$CODEX_THREAD_ID"`, which keeps the command from matching Codex's allow rule) as an `exec_command` session with escalated (unsandboxed) permissions, since `codex queue` must write `~/.codex`, and end the turn. The first event is queued into your thread and the waiter exits. When woken, handle it, then rearm with `--head` set to the head you just handled. Don't pipe the waiter into `codex queue` yourself.

The waiter makes one GraphQL call a minute, for the repo of the current directory (pass `--repo owner/name` if you are elsewhere). The last reported draft flag, review decision, and blocked heads are remembered, so a change made between one waiter's exit and the rearm is reported by the next one. Never poll in a background shell, and never chain scheduled wakeups.

## When woken

- **Head moved:** record the old SHA from the event, then `git fetch origin && git log <old>..<new> --stat` and `gh pr diff <number>`. Report what changed. If you were watching for something specific, re-evaluate it against the new state. If you are on the PR's branch, `git pull --ff-only`; never switch branches to get there.
- **Ready for review:** someone wants it reviewed now. Keep `--comments` if it's yours, and rearm.
- **Conflicts with its base:** reported once per head, when GitHub says `CONFLICTING`, and at once if you arm on a PR that already conflicts. Rebase onto `origin/<base>` (if the base PR just merged, see the stacked-PR step below), run the tests, push with `--force-with-lease`, check that `gh pr view <n> --json mergeable` says `MERGEABLE`, tell your reviewer, and rearm.
- **CI passed (`--ci`):** the current head has finished CI successfully. Continue the review or merge-readiness work, then rearm without `--ci`.
- **CI failed:** reported once per head, after every check on it has finished. Required checks count when the PR has any; otherwise every check does. Read `gh pr checks <n>` and the failed job's log. Fix it and push, or rerun a flaky job (`gh run rerun <run-id> --failed`), tell your reviewer when it's green, and rearm.
- **Stacked PR, base merged:** GitHub retargets your PR to the base's own base. If that merge was a squash, your branch still carries the base's original commits and usually conflicts. Rebase only your own commits (`git rebase --onto origin/main <base's last commit> <your branch>`), run the tests, push with `--force-with-lease`, check it's `MERGEABLE`, and rearm.
- **Back in draft:** more work is wanted before review. Look for what in the PR's comments; if nothing says, ask in your final message. Rearm.
- **Review decision `APPROVED`:** report it and rearm. Don't merge unless you were told to.
- **Review decision `CHANGES_REQUESTED`:** the reviewer's comments arrive as their own event, or in the same line; handle those. If none are visible, read `gh pr view <n> --json reviews`.
- **Review decision `REVIEW_REQUIRED` or `none`:** an approval was dismissed (often by a push) or the requirement changed. Note it and rearm.
- **New comments:** the event names each comment's author and location. Make any fix that is clearly asked for. Reply in the comment's own thread, starting with `🍋 <your signature>:`, if you are allowed to post; otherwise draft the reply in your final message for your human to post. Then rearm.
- **Merged or closed:** nothing is left to watch, whether you wrote the PR or reviewed it. Stop the waiter with `lemonaid watch stop --self pr <number>` (in Codex, don't rearm), never `pkill -f` the command, which stops every lemon's matching waiter, and end your turn with one line saying so.

## Notes

- One `gh` call per minute per watched PR. To watch many PRs, run one waiter per PR, or ask before starting dozens.
- `lemonaid watch pr --help` lists every flag. State and locks live in `$TMPDIR/watch-pr`; deleting them breaks duplicate detection for every running waiter.
