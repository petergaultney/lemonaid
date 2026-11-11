---
name: triage-notifications
description: Triage your user's unread GitHub notifications - mark read what their rules cover, and put the rest in a triage doc they approve by checkbox. Use when woken by `lemonaid watch notifications`, or when asked to triage or clean up GitHub notifications.
---

# Triage GitHub notifications

Your user's GitHub notifications pile up faster than they read them. You keep them small: you mark read what their rules say they never need, and what they have already acted on, and you show them the rest in a document where one checkbox clears a group.

## Commands

All GitHub access goes through `lemonaid github notifications`; don't compose `gh api` calls.

```bash
lemonaid github notifications list --json      # unread threads, with details
lemonaid github notifications show <id> --json # one thread, read or not
lemonaid github notifications read <id> ...    # mark threads read
```

Each thread has `thread_id`, `repo`, `reason` (why GitHub notified them: `mention`, `review_requested`, `assign`, `author`, `comment`, `state_change`, `subscribed`...), `type`, `title`, `updated_at`, and for a PR or issue `number`, `html_url`, `state`, `merged`, `draft`, `author`, `my_review` (their latest review), `latest_commit_at`, `my_last_activity_at`, and `acted`. `acted` is true when their account wrote, after the thread's latest activity, a submitted review or comment that doesn't start with the lemon marker. Lemons post as your user and start what they write with it, so any other is theirs.

## When

Subscribe with `lemonaid watch notifications --wait` in your brief's `## Watching` (`--every MINUTES` sets the batch interval, 30 by default). Each batch lists the threads that are new or active since the last. Triage the whole unread list each time, not only the batch: earlier threads may have changed.

## What you may mark read without asking

Only these, and nothing else:

1. **Threads your user's rules cover.** The rules are prose in this skill's overlay (below, if your user wrote one). A rule is your user's instruction; apply it as written, and when a thread only arguably matches, leave it for them.
2. **Mentions and review requests your user has acted on:** `reason` is `mention`, `team_mention`, `review_requested` or `assign`, and `acted` is true, or the PR or issue is merged or closed. `lemonaid watch mentions` and `watch reviews` already woke a lemon for these; a wake doesn't mean your user read the comment, so until they act, keep these at the top of the triage doc.

Mark them read with one `read` call, and record each group you read under "Read for you" in the triage doc with the rule or reason, so your user can see what you did on their behalf.

## The triage doc

Keep one Markdown document for your user, listed in your brief's `## Docs` with Watch `All edits`, where they will look for it. Your user's overlay may name its path. Write it fresh each triage:

- **Needs you:** unread mentions, review requests and assignments they haven't acted on, one bullet each with its link.
- **Groups:** everything else, grouped by what your user would do about it (a project, a repo, "merged PRs you commented on"), ranked by their priorities. Each group is one checkbox, `- [ ] <label> (<n> threads)`, with its threads below it as links and their thread ids.
- **Read for you:** what you marked read since they last looked, by rule.

When your user checks a group, mark its threads read and remove the group. When they write a Relay comment such as "always dismiss these", propose the rule it implies as a reply, and add it to the overlay (`~/.lemons/skills/triage-notifications/overlay.md`) only once they agree.

## Ranking

Without other priorities from your user, rank by how much someone is waiting on them:

- `review_requested` on open PRs: someone is blocked on them.
- `mention` and `assign` on open threads: direct engagement expected.
- `comment` on PRs they authored: their code is being discussed.
- `comment` on threads they took part in: may need a follow-up.
- `state_change` and `subscribed`: usually information only.
