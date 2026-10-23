# Patch

#### Fixed

- **Many lemonaid processes starting at once no longer crash on `database is locked`.** Each new process took an exclusive lock on the inbox database to check for migrations, so dozens of watchers restarting together could wait out sqlite's 5-second busy timeout and die at startup. A process now takes that lock only when a migration is pending, and waits up to 30 seconds for any other lock.
