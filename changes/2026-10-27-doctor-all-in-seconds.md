# Patch

#### Fixed

- **`lemon doctor --all` finishes in seconds.** With about a thousand attached briefs it took many minutes at full CPU, because it reread every brief and every running waiter for each lemon; it now reads them, and asks `ps` about every terminal, once per run.
