# Minor

#### Changed

- **Every lemon's push scout runs in one scout host process.** `watch --self --push` registers the lemon under `scouts/` in the state directory and starts `lemonaid watch host` if none runs, in place of one process per lemon (about 53 MB each). Stopping one lemon's scout removes its registration, and restarting any scout restarts the host, which brings every scout back on the installed code.
