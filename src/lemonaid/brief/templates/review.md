Hidden: yes

## Now

## Questions

## Next

## PRs

## Docs

## Done

## Goal

A cross-harness review of $pr_link, with a verdict, in the review doc at $output_doc_link.

## Executive Summary of Results

## Context

## Acceptance Criteria

## Limits

Don't post to GitHub, push, merge, or edit the author's worktree. Findings go only in the review doc, never in this brief or on the PR.

Write the review verdict in `## Executive Summary of Results`, including any critical findings or that the PR is clear.

Write the review doc at `$output_doc`. When it's written, $tell a one-line pointer to it.

On a re-review after the author pushes, run `git range-diff origin/<base> <reviewed sha> HEAD`, where `<base>` is the PR's base branch (`gh pr view <n> --json baseRefName`) and `<reviewed sha>` is the `Reviewed head` in the review doc. Attribute a finding only to a commit in `origin/<base>..HEAD`. `<reviewed sha>..HEAD` is wrong after a rebase: it includes base-branch commits the PR didn't write.

Set no status for as long as the PR is open, whatever your verdict, and say under `### Waiting on` what comes next: the author while you ask for changes, and the merge once you approve. Keep `lemonaid watch --self` armed until then and rearm after handling every source in its batch. When the PR merges or closes, remove its row and subscription and set yourself `done`. Keep document rows and the unified watcher until your session is removed, since comments on those docs still need a reply. Use `lemonaid watch stop --self` when the session ends; never `pkill -f` a waiter command, which stops every other lemon's matching waiter too.

## Watching

Read the current PR and review doc first. The commands below are subscriptions; `lemonaid watch --self` reads them. Claude: follow the watch rule in the `brief` skill, which relies on the push scout when it is running and starts the one background Bash watcher only when it is not. Codex: run that one watcher with `--codex-thread` in an escalated exec_command session. Rearm it after handling each batch.

- `lemonaid watch pr --wait $pr_url --comments --ci --me 'Reviewer ($wordybin)'`
- `lemonaid watch doc --wait $output_doc_arg --me 'Reviewer ($wordybin)'`
