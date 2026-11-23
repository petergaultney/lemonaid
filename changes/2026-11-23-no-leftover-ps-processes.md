# Patch

#### Fixed

- **The scout host no longer keeps finished `ps` and `gh` processes as zombies.** A restart replaced its code while scouts still had those running, and nothing in the new code collected them; it now does as it starts.
- **A Codex lemon's sandboxed shell no longer tries to run `ps`.** macOS refuses the setuid `ps` there, which logged `could not list Codex processes: Operation not permitted` a few times a minute; lemonaid now treats the processes as unknown without trying.
