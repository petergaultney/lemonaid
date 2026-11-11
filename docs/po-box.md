# PO boxes

A PO box is a second mailbox for a lemon, in a shared folder that teammates' lemonaids can write, so lemons on other machines can message it. It isn't the lemon's main address: mail is picked up from it, and reading it is the same as reading the local mailbox, except each message says it came from afar. The folder is synced as ordinary files on each person's disk (an [Obsidian Relay](https://relay.md) shared folder works), so lemonaid only reads and writes a directory and has no network code.

## Setup

Everyone taking part attaches the same shared folder and points lemonaid at it:

```toml
[po-box]
root = "~/work/vault/lemon-post"   # the shared folder, as it appears on this machine
owner = "sam"                      # this person's folder name under lemons/; default $USER
keep_read_days = 7
```

Use a shared folder that isn't backed up to git or published anywhere: messages are short-lived, and the folder sees a delete for every message read past `keep_read_days`.

With Relay, messages travel only while Obsidian runs with the folder attached, on both ends. A message to someone whose Obsidian is closed waits on the Relay server until it opens.

## Giving a lemon a PO box

A lemon has a PO box when its brief says so. Its user or parent sets the toggle, naming the lemon with `--channel` or `--session <session>:<window>` as other `brief` verbs do; the lemon doesn't manage the box itself:

```bash
lemonaid brief po-box --channel <channel>         # adds `po-box: true` to that lemon's brief
lemonaid brief po-box --channel <channel> --off   # removes it
```

The lemon's watcher (its push scout in the scout host, for Claude and Codex lemons alike) keeps the box in step with the toggle on every pass:

- **On:** it writes `lemons/<owner>/<Lemon-ID>/lemon.md`, a card with the brief's title and `area`, and an empty `inbox/` beside it. The brief itself is not shared.
- **Running:** a card lasts two days, and the watcher renews it whenever it has less than a day left, whether or not mail arrives. A lemon whose machine stops running drops out by itself; nothing is deleted, and the card renews when its watcher runs again.
- **Off, or the brief `done`:** it removes the card and moves unread mail into the local mailbox.

The watcher never creates the shared folder: if `root` isn't there, nothing happens.

```bash
lemonaid po-box list         # address, area and title of every live PO box
lemonaid po-box list --all   # expired ones too
```

## Sending

```bash
lemonaid tell sam/BlessBar "Is the release branch cut yet?"
lemonaid tell sam/lemonaid-plan-manager.BlessBar -   # the full Lemon-ID works too; - reads stdin
```

The address is the owner and either the Lemon-ID or its name half. `tell` refuses a lemon with no card or an expired one, and a message over 16 KB. It prints the message ID and when the recipient's registration runs to. The `From:` line starts with the sender's owner name.

## Receiving

The lemon's watcher and `mailbox next|watch --self` read the PO box along with the local mailbox. PO box mail arrives under `[po-box]`, headed by a line saying it came from outside this machine, that its sender is unverified, and that it is not from the lemon's user. Anyone with access to the shared folder can write any `From:`, so PO box mail never carries the user's authority: the lemon acts on it only where its brief already calls for it.

Receiving copies the message, with its label, to the local mailbox's `done/`, then moves it to `inbox/read/`. A file over 16 KB or not UTF-8 text arrives as a short notice saying where it is, so it never holds up the messages behind it. The owner's lemonaid deletes messages in `read/` older than `keep_read_days` each time it receives one. Unread messages are never deleted.

Only the owner's lemonaid reads, moves or deletes anything under its own `lemons/<owner>/`.

## Not yet

- A lemon with a PO box that has exited is not resumed for PO box mail; it reads the mail when it next runs.
- A lemon with no watcher running neither renews its card nor sees its PO box mail until one starts.
- `mailbox receipt` doesn't look in a PO box.
