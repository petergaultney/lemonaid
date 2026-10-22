# Patch

#### Changed

- **The watcher's and the inbox's process listings take a tenth of the time on macOS.** `ps` spent most of a second naming each process's terminal, so lemonaid now lists device numbers and names them from `/dev` itself. Linux is unchanged.
