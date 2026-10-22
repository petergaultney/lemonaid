# Minor

#### Added

- **`lemonaid watch restart` restarts running `watch --self` waiters, push scouts included, into the installed lemonaid.** Name lemons by Lemon-ID, or pass `--self` or `--all`. Each waiter restarts once nothing it has detected is waiting to be delivered, with the same arguments, so no lemon has to rearm.
- **A new lemonaid version restarts older waiters by itself.** The first lemonaid command it runs sends the restart to every waiter started by another version. Waiters already running when this version is installed don't know the signal; stop and rearm those once.
