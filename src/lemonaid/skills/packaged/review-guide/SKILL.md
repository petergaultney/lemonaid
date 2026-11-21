---
name: review-guide
description: Write a review guide for a round of changes, ordered for understanding rather than in diff order, open it in the user's editor, watch it and the changed files for review comments, and answer them in their threads. Use whenever you finish a round of changes the user will review, including fixes made after an earlier round, and when the user asks you to commit reviewed work.
---

# Write a review guide

A review guide is a tour of one round of changes. It tells the reader which changes to read first and why, so they don't have to rebuild the order from a diff that is sorted by path. Write one each time you finish a round of changes for review: the first version of a change, and each round of fixes after review comments. The user comments in the guide and in the changed files with lemonaid's comment threads, and you answer in those threads.

The user's own preferences for guides, when they have any, follow this text as an overlay. Where they differ from what is written here, they win.

## Before you write

1. **Name the round's files.** List the paths this round changed, in every repo it touched. A repo may hold other uncommitted changes, yours from other work or the user's, that aren't part of the round; leave them out, and limit every diff below to the round's paths (`-- <paths>`).
2. **Name the diff:** find where the round starts, and list what changed since. Don't use a plain `git diff`: if the user stages hunks as they read, it shows only what they haven't read yet.
   - For the first round, the start is the commit the work began from: `git diff <base> --stat -- <paths>`, plus untracked files from `git status --short`.
   - For a later round, the start is where the previous round ended. If that round was committed, it is that commit. If it wasn't, it is the snapshot the previous guide recorded (below): take a new snapshot and run `git diff --stat <previous snapshot> <new snapshot> -- <paths>`, which covers untracked files too. Without a snapshot, `git diff <base>` repeats the earlier rounds.
3. **Read the whole diff**, so that every changed file appears in the guide, in one of its sections. The user's saved comments show in it as markers and threads sections; describe your own edits, not those.

### Snapshot an uncommitted round

At the end of each uncommitted round, record the state you hand over as a git tree, built in a temporary index so that the user's index is untouched:

```sh
d=$(mktemp -d) && { GIT_INDEX_FILE="$d/index" git read-tree HEAD && GIT_INDEX_FILE="$d/index" git add -A && GIT_INDEX_FILE="$d/index" git write-tree; s=$?; rm -rf "$d"; [ $s -eq 0 ]; }
```

On success it prints the tree's id and exits 0. The tree holds tracked and untracked files and leaves out ignored ones. Record the id only when the command succeeded. Write it in the guide's opening paragraph with the round's paths, one id per repo, so the next round can diff against it over the same paths. git prunes an unreferenced tree after about two weeks, which is long enough for a review.

## Where the guide goes

Put the guide outside the repo, in a folder named after your brief, beside it: for the brief `~/.lemons/brief/2026-11-19-some-work.md`, write `~/.lemons/brief/2026-11-19-some-work/guide-<n>.md`, where `<n>` counts the rounds from 1. `lemonaid brief show --self` names your brief's file. Not in the brief folder itself: lemonaid treats every `.md` file there as a brief. Without a brief, ask the user where it goes. Write a new file for each round, and leave earlier guides as they are, since they hold the comment threads of their round.

## What the guide says

Open with one paragraph: what the round is, where the changes are (repo, branch, base commit, committed or not, and the round's snapshot when it isn't committed), who reviewed it and their verdict, and how it was tested. End it with an invitation to comment in the guide or in the files.

Then these sections, in this order, leaving out any that would be empty:

- **Core changes, most significant first.** A numbered list. Each item opens with a bold sentence that says what the change does, then gives the reason in a sentence or two, and the decision behind it when that isn't obvious. Group the hunks that implement one idea into one item, even across files, so the reader reads them as code together. End the item with its locations.
- **Consequential changes.** Changes made because of the core ones: call sites, imports, renames, docs, edits that make the types pass, and the tests. One bullet each, shorter than a core item. The reader may skim these or accept them as a group.
- **Changes you can skip.** Mechanical changes: moved tests, formatting, generated files. One line each.
- **Decisions you made along the way.** Decisions the user made in this session that the code reflects, with where they are recorded. It reminds the user of what they already chose, so they don't review it again.
- **Known limits.** What the round doesn't do or handles imperfectly, and anything the user must do themselves, such as an install step.

Write for this reader. A user who worked the change out with you in this session doesn't need its background again; name the decision and move on. A reader new to the change needs the background before the first core item. Write each paragraph and bullet on one line, so the editor wraps it at its own width.

Comments live in the file only for Python and Markdown files. When the round changes a file of another kind, say in the guide that comments on it go in the guide, beside its entry.

### Point at the code

Give every claim a location the reader can jump to with one key. Write each as `` `path:line` `` or `` `path:line-line` ``, with a path that starts with `~/` or `/`, since the guide is outside the repo and the editor resolves a relative path against its own working directory. Point at the line where the logic is, not the top of the file. Line numbers go stale as the code changes, so name the function or class too: `` `~/repo/src/pkg/sync.py:41` (`note`) ``.

## Open it and watch for comments

1. **Open the guide** in the user's editor: `lemonaid editor open <guide>`. If it fails, give the user the guide's path in chat, with the command's message, since it says why: no editor server, none in this terminal workspace, or an editor that refused. Say the guide is open only when the command succeeded.
2. **Watch the guide and every file the round changed:** `lemonaid brief doc add --self <path> "review" --watch "All edits"` for each one. That only records the subscription; check that something delivers it with `lemonaid watch --self --status`, and if no watcher runs, start one as the `brief` skill says. Without a brief, use the `watch-doc` skill for each file.
3. **Tell the user**, in chat, the guide's path and which files you watch. The watcher reads files on disk, so a comment wakes you once the user saves the file it is in (their editor may save it for them). Then end the turn.

Keep watching until the user says the review is done. When the round is committed, remove the rows you added for its files: `lemonaid brief doc rm --self <path>` for each, so the brief's Docs table holds only what is still under review.

## Answer comments

Read and answer with `--self`, which signs with the same name your watcher counts as yours for that file, so your own replies never wake you:

```sh
lemonaid comments list <path> --unanswered --self
lemonaid comments reply <path> --re <id> --self "<body>"
```

`list` marks each comment waiting on you `UNANSWERED`, with its id; pass that id to `--re`, even when it is a reply deep in a thread. Without a brief, `--self` has no signature to find; sign with `--as` and read with `--me`, both the name you pass to `watch-doc`'s `--me`.

Never edit a threads section by hand, and never remove a record: if you posted a comment by mistake, ask the user to delete it.

If someone answered the same comment while you were writing, `reply` refuses, and prints the comment and the replies you haven't read. Read them. If yours adds nothing, don't post it. If it still adds something, say only that, and send it again with the `--after <id>` the refusal names.

Your comment or reply also shows in the user's inbox, so they hear of it even when the file isn't open in their editor.

- If a comment asks for a change, make it, then reply with what you changed and where (`path:line`).
- If it asks a question, answer it in the thread. Keep the reply to one to three sentences; if the answer needs more, change the guide or the code and point the reply at the change.
- Leave resolving to the user. Don't resolve or strip their comments during the review.

The user may also comment with Relay or plain CriticMarkup (`{>>...<<}`) in a Markdown file, beside its threads; the watcher wakes you for those too. Answer them in place, as the `watch-doc` skill says.

## Keep comments out of commits

When the user asks you to commit reviewed work:

1. Run `lemonaid comments strip <path>` on each file you are committing that has threads, and go on only if it exits 0. If one of its threads is unresolved, ask the user first.
2. Check that the file on disk is clean: `grep -n 'lma:' <path>`. Don't use `lemonaid comments list` here, since it reads the editor's buffer. If the threads header is still there, the user's buffer had unsaved changes and the strip went into it; ask them to save the file, then check again. A marker-shaped example in the code, such as one in a fenced block, stays after a strip and is not a comment.
3. Right before you commit, check what the index holds for those files, in two ways, since a hunk the user staged keeps its comment lines whatever happens to the working file:
   - the staged files themselves, for markers and threads headers: `git grep --cached -n -E '\[/?lma:' -- <paths>`;
   - the staged additions, for comment and resolution records, which can be staged without their header: `git diff --cached -U0 -- <paths> | grep -nE '^\+.*\{"(id|resolves)": ?"'`.

   A match is a comment unless it is an example in the code that the working file holds too. If a comment is staged, stop and ask the user to unstage those lines, then check again. Don't restage the whole file: if the user stages hunks as they read, that discards their record of what they have read.

## Learn the reader's preferences

When the user says how they want guides written ("put the tests next to the change they exercise", "skip the docs"), propose an entry for this skill's overlay, `~/.lemons/skills/review-guide/overlay.md`, and add it once they agree. Write it as an instruction to the next guide's writer, with the reason when the user gave one. Then run `lemonaid skills install review-guide`, which renders the skill again with the new entry.
