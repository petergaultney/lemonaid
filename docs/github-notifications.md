# GitHub notifications

`lemonaid github notifications` lets a lemon keep your GitHub notifications small: it marks
read what your rules say you never need and what you have already acted on, and shows you
the rest in a document where one checkbox clears a group. The `triage-notifications` skill
([Skills](skills.md)) teaches a lemon the workflow; this page is the commands.

```bash
lemonaid github notifications list             # unread threads, one line each
lemonaid github notifications list --json --scope org:acme
lemonaid github notifications show 1234567890 --json
lemonaid github notifications read 1234567890 1234567891
```

`list` prints your unread threads, with what triage needs: the PR or issue's `state`,
`merged`, `draft`, `author`, your latest review (`my_review`), the latest commit, and
`acted`. `acted` is true when your account wrote a review or comment after the thread's
latest activity that doesn't start with the lemon marker: lemons post as you and start
what they write with it, so any other is yours. Pending (unsubmitted) review comments
don't count. Only each subject's 30 latest comments, 20 latest reviews and the
latest replies on its 20 latest review threads are read for this. Subjects are read in
GraphQL batches of ten, four batches at a time, so a few hundred threads take seconds.

`show` prints one thread, read or not. `read` marks threads read; it is the only command
here that changes anything on GitHub, and it exits 1 if any thread failed.

## Waking a lemon to triage

`lemonaid watch notifications` wakes a lemon with the unread threads that are new, or
active, since it was last told, at most once per `--every` minutes (30 by default). It is
read-only.

```bash
lemonaid watch notifications --wait --every 60 --once
lemonaid watch notifications --status
```

The first waiter takes what is already unread as seen; `--backlog` reports it instead. A
thread you read in the meantime is dropped from the cursor and reported again only if it
becomes unread. `--scope`, `--once`, `--codex-thread` and `--state-dir` work as in
[`watch reviews`](watch.md#watching-for-review-requests). Subscribe through a brief's
`## Watching` section:

```markdown
## Watching

- `lemonaid watch notifications --wait --every 30`
```

Stop it with `lemonaid watch stop --self notifications`.

`watch mentions` and `watch reviews` still wake a lemon within minutes for a mention or a
review request; the triage skill keeps those threads unread until you act on them.
