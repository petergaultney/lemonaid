# Patch

#### Fixed

- **The inbox no longer freezes for up to a second every 10 seconds.** The `ps -A` listing behind the `deaf` and `dead` marks now runs on a background thread instead of the event loop.
