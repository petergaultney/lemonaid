---
name: watch-doc
description: Wait, at zero token cost, for a human to respond to a Markdown document via Relay Comments (or body edits), then reply inline in the same thread. Use whenever a document you wrote is the channel for feedback - reviews, design drafts, anything a human will annotate in Obsidian.
---

# Watch a document for Relay Comments

You wrote a document; the human reads it in Obsidian and responds with Relay Comments (inline CriticMarkup). This skill is how you wait for that without spending tokens, and how you reply so the conversation stays in the document.

## Arguments

`<doc-path>` (absolute). Optional: `--edits` also reports body edits after they have been quiet for 45 seconds.

## Reply identity

Sign your replies with one name and pass the same name to the waiter as `--me`: `$LEMON_NAME` if set, else your harness's name (`Claude`, `Codex`). Any name you signed with before in this doc is a legacy name: pass it as `--legacy <name>`, repeated for each, and replies signed with it count as yours.

Reply blocks look like `{{authorId="<id>" author="<name>">>...<<}}`. Relay shows only `author`; use an `authorId` that lets a reader find the session that wrote the reply, such as your tmux session name.

If `--me` and the `author` of your reply blocks differ, the waiter sees your own replies as unanswered and wakes you on them.

## Waiting

Tell the human the doc is ready, with its absolute path.

Before starting a waiter, check for one: `lemonaid watch doc --status <doc> --me <name>`, and again with each legacy name in case an older waiter is still up. If one is running, you are already watching; don't start another. A second waiter for the same doc and name refuses to start. Then read the doc and handle any unanswered threads; the waiter reports only threads that are new or have changed since a waiter last reported them.

The waiter reads the document every 15 seconds. It reports when a thread becomes unanswered or an unanswered thread gains a block, and with `--edits` when body edits have been quiet for 45 seconds.

In Claude Code, start the waiter with `--once` as a background Bash task and end the turn:

```
Bash(
  command: lemonaid watch doc --wait <absolute-doc-path> --me <name> [--legacy <old name>] [--edits] --once,
  description: "Wait for Relay Comments on <doc basename>",
  run_in_background: true,
  timeout: 2147483647,
)
```

It prints the first event and exits, and the task's completion wakes you. Handle every unanswered thread, then rearm by starting the same command again before ending that turn. A thread you left unanswered on purpose does not wake the new waiter; a comment that arrived while you worked wakes it at once.

- Don't use `Monitor`: it expires after 30 minutes and wakes you for nothing.
- Don't run the waiter without `--once` in background Bash: its output goes to a file and never wakes you.
- Pass `timeout: 2147483647`. Claude Code stops a background task after 30 minutes by default, and after its `BASH_MAX_TIMEOUT_MS` ceiling otherwise. If the harness stops the waiter anyway, rearm it, whatever the notice says.

In Codex, first check that `CODEX_THREAD_ID` is set and `codex queue --help` succeeds; if either fails, report that setup problem instead of claiming the watch is active. Start `lemonaid watch doc --wait <absolute-doc-path> --me <name> [--legacy <old name>] --codex-thread "$CODEX_THREAD_ID"` as an `exec_command` session with escalated (unsandboxed) permissions, then end the turn normally. Inside the workspace sandbox `codex queue` cannot write `~/.codex`, so the waiter checks that and prints `not started: cannot write ...` instead of waiting for an event it could not deliver. Don't call `functions.wait`: keeping a turn open makes ordinary user steering interrupt the watcher. On the first event the waiter queues a message into your thread and exits. Handle every unanswered thread, then rearm by starting the same command again before ending that turn.

In OpenClaw, nothing inside a turn can wait. Instead each session gets one long-lived waiter that watches every doc on that session's list and runs one agent turn in the session per event. Get your session key from the `session_status` tool, then run `lemonaid watch openclaw start <absolute-doc-path> --session-key <your session key> --me <name>` through `exec`, and sign reply blocks with your session key as `authorId`. This adds the doc to your session's list, takes it off any other session's list (the latest writer wins), and starts the waiter if it isn't running. A doc drops off the list after 7 days with no comment, and there is nothing to rearm. `lemonaid watch openclaw list` shows every watched doc, and `stop <doc>` removes one.

Never use a hand-rolled polling loop or scheduled wakeups; they wake the session with nothing to do.

## What a Relay Comment looks like

```
{==the text being commented on==}{{authorId="<relay user id>" author="<Display Name>">>the comment<<}}
```

- The `{==...==}` highlight may be absent (a comment anchored to a point).
- A thread is the highlight plus every `{{...>>...<<}}` block that immediately follows it, with nothing in between. Replies are appended as further blocks. A thread is **unanswered** when its last block's `author` is not your name or a legacy name. Human authors are never matched by name; anyone can comment, and several people can share a thread.
- A human may also just edit your prose. Don't revert it. If an edit changes a conclusion you disagree with, add a comment block beside it saying so.

To find unanswered threads by hand, `rg -o 'author="[^"]*">>' <doc-path>` lists the blocks in order.

## Replying

- Use a surgical edit: the old text is the whole thread as it currently stands (highlight plus blocks, verbatim). The replacement is the same thread with `{{authorId="<id>" author="<name>">>your reply<<}}` appended directly after the last block. Add no newline or space between blocks, or the plugin and the waiter will see two threads.
- Never edit or remove a human's comment block or highlight.
- Replies are one to three sentences. If the answer needs more, change the document body and have the reply point at the change.
- If the comment asks for work (check something, run something), do it first, then reply with the result.
- The document may be live-synced while a human types in it. After the first write, make every change a surgical edit with a small old string, never a whole-file rewrite.

## Stopping

Only a human telling you the document conversation is over ends the watch. Stop the waiter (`TaskStop` the background task in Claude Code; in Codex, end the exec session or don't rearm; in OpenClaw, `lemonaid watch openclaw stop <doc>`), then confirm `--status` says `no waiter running`. A "thanks" or one answered question does not end the watch; the human may keep commenting.

## Notes

`lemonaid watch doc --help` lists every flag. State and locks live in `$TMPDIR/watch-doc`; deleting them breaks duplicate detection for every running waiter.
