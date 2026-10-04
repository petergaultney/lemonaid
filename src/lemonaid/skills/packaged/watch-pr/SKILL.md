---
name: watch-pr
description: Wait, at zero token cost, until a GitHub PR gets a new push, is merged/closed, is marked ready for review or back to draft, changes review decision, or (with --comments) gets a new comment from someone else, conflicts with its base, or fails CI, then wake and act on it. Use on every PR you open (with --comments), and when waiting on someone to update a PR you've reviewed or are watching.
---

# Watch a PR for pushes, state changes, review comments, conflicts, and failed CI

## Arguments

A PR number or URL. If omitted, infer it from the current branch (`gh pr view --json number`).

- `--comments --me "<your signature>"`: also wake on new comments from anyone but you, and, as the PR's author, when it starts conflicting with its base or its CI fails. Use it on every PR you open. `<your signature>` is the one you sign Relay Comments with, e.g. `Author (MotorHoe)`.
- `--legacy <name>`: another signature whose comments count as yours, e.g. one you signed with before (repeatable).
- Without `--comments`: pushes, merge/close, draft/ready, and review decision only, e.g. when you reviewed someone else's PR. Conflicts and CI are the author's to fix, so a reviewer isn't woken for them.

A comment counts when it is in an unresolved, non-outdated review thread, a submitted review's body, or the PR conversation. Lemons usually post with their human's GitHub account, so sign everything you post right after the marker: `🍋 Author (MotorHoe): ...`. A comment is skipped as yours only when it starts with 🍋, then your `--me` or a `--legacy` signature, then a colon. Every other comment wakes you, including other lemons' 🍋 comments, signed or not. Bots and pending (unsubmitted) review comments never count. Comments already reported to `--me` are remembered, so a rearm doesn't wake you on one you handled but left unresolved.

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
- **CI failed:** reported once per head, after every check on it has finished. Required checks count when the PR has any; otherwise every check does. Read `gh pr checks <n>` and the failed job's log. Fix it and push, or rerun a flaky job (`gh run rerun <run-id> --failed`), tell your reviewer when it's green, and rearm.
- **Stacked PR, base merged:** GitHub retargets your PR to the base's own base. If that merge was a squash, your branch still carries the base's original commits and usually conflicts. Rebase only your own commits (`git rebase --onto origin/main <base's last commit> <your branch>`), run the tests, push with `--force-with-lease`, check it's `MERGEABLE`, and rearm.
- **Back in draft:** more work is wanted before review. Look for what in the PR's comments; if nothing says, ask in your final message. Rearm.
- **Review decision `APPROVED`:** report it and rearm. Don't merge unless you were told to.
- **Review decision `CHANGES_REQUESTED`:** the reviewer's comments arrive as their own event, or in the same line; handle those. If none are visible, read `gh pr view <n> --json reviews`.
- **Review decision `REVIEW_REQUIRED` or `none`:** an approval was dismissed (often by a push) or the requirement changed. Note it and rearm.
- **New comments:** the event names each comment's author and location. Make any fix that is clearly asked for. Reply in the comment's own thread, starting with `🍋 <your signature>:`, if you are allowed to post; otherwise draft the reply in your final message for your human to post. Then rearm.
- **Merged or closed:** nothing is left to watch, whether you wrote the PR or reviewed it. Stop the waiter (`TaskStop` the background task in Claude Code; in Codex, don't rearm) and end your turn with one line saying so.

## Notes

- One `gh` call per minute per watched PR. To watch many PRs, run one waiter per PR, or ask before starting dozens.
- `lemonaid watch pr --help` lists every flag. State and locks live in `$TMPDIR/watch-pr`; deleting them breaks duplicate detection for every running waiter.
