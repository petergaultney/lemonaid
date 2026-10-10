## Goal

A cross-harness review of $pr_link, with a verdict, in the review doc at $review_doc_link.

## Context

## Limits

Don't post to GitHub, push, merge, or edit the author's worktree. Findings go only in the review doc, never in this brief or on the PR.

## Output

Write the review doc at `$review_doc`. When it's written, $tell a one-line pointer to it.

Set no status for as long as the PR is open, whatever your verdict, and say under `### Waiting on` what comes next: the author while you ask for changes, and the merge once you approve. Keep both waiters below armed until then, and rearm each after handling its event. When the PR merges or closes, stop them and set yourself `done`. Stop them with `lemonaid watch stop --self`; never `pkill -f` a waiter command, which stops every other lemon's matching waiter too.

## Waiters

Arm both once your review is written. Make each one-shot for your harness: add `--once` for Claude, or a bare `--codex-thread` for Codex (no `$$CODEX_THREAD_ID`: a shell variable keeps the command from matching Codex's allow rule). Pass the PR head you reviewed as `--head`, and on every rearm the head you just handled, so a push or merge in between is still reported.

- `lemonaid watch pr --wait $pr_number --repo $pr_repo --head <head SHA> --me 'Reviewer ($wordybin)'`
- `lemonaid watch doc --wait $review_doc_arg --me 'Reviewer ($wordybin)'`
