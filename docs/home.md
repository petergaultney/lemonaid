# Where briefs and messages live

Briefs and message inboxes live in `~/.lemons/`:

```text
~/.lemons/
  brief/                one Markdown brief per unit of work
  inbox/<lemon-id>/     unread messages for that lemon; done/ holds read ones
  migrations/<stamp>/   a migration's inventory, database backup, and the old home
  cutover               written by the migration; marks ~/.lemons/ as active
```

Older installs kept both in `~/.brief-lemons/` (briefs at its top level, inboxes in `inbox/`). Lemonaid keeps using `~/.brief-lemons/` until `lemonaid home migrate` has moved it, so upgrading changes nothing by itself. A machine that never had `~/.brief-lemons/` uses `~/.lemons/` from the start.

Only the active home counts: brief commands refuse a brief outside it, and messages go to its inbox. Other files under `~/.lemons/`, including a `brief/` folder made by hand, don't make it active; only `cutover` does.

## Migrating

```bash
lemonaid home migrate --dry-run   # what would move, and what would stop it
lemonaid home migrate --pause     # stop brief and message commands, so waiters can be stopped
lemonaid home migrate             # move everything (continues from a pause)
lemonaid home migrate --reconcile # bring in files written to ~/.brief-lemons/ after cutover
lemonaid home migrate --abort     # undo a migration that stopped before its move
lemonaid home migrate --rollback  # go back, if nothing has changed since
```

Every form takes `--json`.

**What stops a migration.** A real run refuses, changing nothing, while any of these is true. `--dry-run` lists them all:

- an inbox waiter holds its lock (the dry run names each Lemon-ID);
- the Codex delivery service is running;
- a file under `~/.brief-lemons/` is a symlink, or isn't a regular file or directory;
- `~/.brief-lemons` itself is a symlink;
- `~/.lemons/`, or a folder inside it that a file would be copied into, is a symlink or not a directory;
- a destination file already exists;
- the database names a brief under `~/.brief-lemons/` that doesn't exist;
- the migration has already run.

**While it runs.** Every brief and message write holds a shared lock (`home.lock` in lemonaid's state directory) and checks for the pause while holding it. The migration writes the pause and then takes that lock exclusively, so it waits for every write that got in first, however long it takes. After that, brief and message commands refuse with "migration in progress", and the brief view shows the same. That includes reading a brief, sending, and arming an inbox waiter. Only commands from this version check the pause. So an old `lma`, scratch pane, or waiter must be restarted on the new install first. The waiter check sees old waiters too, since it tests the lock they hold.

**The steps.**

1. Pause.
2. Inventory every file with its SHA-256, and back up the database.
3. Copy each file to a partial name, check its hash, and publish it with a hard link, which never replaces an existing file.
4. Recheck every source against the inventory. An editor's save in the meantime stops the run.
5. Rewrite the database's brief paths in one transaction: attachments, pending attachments, and Lemon-ID registrations.
6. Rename `~/.brief-lemons/` into `migrations/<stamp>/brief-lemons`. It is kept as the backup and never deleted.
7. Verify that the backup holds exactly the inventoried files, that they match the new copies, that `~/.brief-lemons/` hasn't been recreated, that no folder in `~/.lemons/` has become a symlink, and that no waiter has armed.
8. Write `cutover` and lift the pause.

**When it stops.** A run that stops leaves the pause in place and says why. Rerun to continue from where it stopped: copies that already match are skipped, and a file whose copy was interrupted is left only under a partial name carrying the migration's stamp (`.<name>.lemonaid-migrate-<stamp>.tmp`), which the rerun removes and copies again. Cleanup only ever touches its own stamp's partial files. Or use `--abort` before step 6, which rewrites the database back, removes partial files and the copies whose hash still matches, and lifts the pause. Nothing is overwritten at any step. A stop after step 6 can only be finished by a rerun, or recovered by hand from `migrations/<stamp>/`.

**After cutover.** If `~/.brief-lemons/` appears again (an editor saving a buffer it opened before the migration, or an older lemonaid), every brief and message command refuses, and the migration reports it if it happened before the migration finished. `--reconcile` pauses, moves each late file into the new home at the path the migration would have given it (never over a different file), repoints any database row that names it, and removes the old root once it is empty. A late file that differs from the new home's copy stops `--reconcile` with nothing changed, naming both, for a person to merge. It repoints the database before moving any file and keeps its pause until no file or row is left in the old home, so a `--reconcile` that stops partway is finished by running it again; `--abort` won't lift its pause. A symlink at `~/.brief-lemons` is never followed: `--reconcile` refuses it, and it has to be removed by hand.

**Rollback.** `--rollback` pauses and takes the lock as the migration does, then refuses, lifting the pause and changing nothing, unless the new home holds exactly what was copied: no brief edited, no message sent or read, nothing added. Then it rewrites the database back, renames the backup to `~/.brief-lemons/`, and moves the copies out of the new home into `migrations/<stamp>/rolled-back/`. Nothing is deleted.

**Rehearsing.** `LEMONAID_LEMONS_DIR`, `LEMONAID_LEGACY_BRIEFS_DIR`, and `LEMONAID_DB` point a migration at copies. `LEMONAID_BRIEFS_DIR` or `LEMONAID_MESSAGES_DIR` pin one folder, and the migration refuses while either is set. `scripts/sandbox` sets all of them to folders in `.z/sandbox/`.

## Rollout on a machine with running lemons

1. Upgrade the install. Restart `lma` and any scratch pane, and close or revert editor buffers visiting files in `~/.brief-lemons/`: nothing can stop an editor from saving there, so one left open recreates the old home after cutover.
2. Run `lemonaid home migrate --dry-run` and note the armed waiters it lists.
3. Run `lemonaid home migrate --pause`. From here a Claude lemon whose waiter exits can't rearm it: the rearm fails with "migration in progress" rather than racing the migration.
4. Have each lemon stop its waiters with `lemonaid watch stop --self`, or stop each by the pid in its `.waiter.lock`. Never `pkill -f` a pattern, which matches every lemon's waiter.
5. Run `lemonaid home migrate`. If it reports that the old home exists again, run `--reconcile`. Then have each lemon rearm.
6. Update anything outside lemonaid that names `~/.brief-lemons/`: prompts, skills, and other watchers.
