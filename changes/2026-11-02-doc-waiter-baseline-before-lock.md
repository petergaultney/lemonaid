# Patch

#### Fixed

- **`lemonaid watch doc` reports an edit made just after it starts.** It reads the document before taking its waiter lock, so once `--status` says a waiter is running, any later edit wakes it.
