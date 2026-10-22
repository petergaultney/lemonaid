# Patch

#### Changed

- **`lemonaid watch restart` lists the watchers it cannot signal.** It names each one's lemon, kind, pid and rearm command instead of only counting them.

#### Upgrading

- **Restart older watchers once by hand.** Watchers and push scouts started before `lemonaid watch restart` existed don't know its signal. Run `lemonaid watch restart --all`, then `kill` each listed pid (never by pattern) and rearm it; steps are in `docs/watch.md` under "Restarting watchers after an upgrade".
