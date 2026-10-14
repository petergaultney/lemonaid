# Patch

#### Changed

- **A Claude lemon is told when its push scout starts, and told loudly when it is not on push.** The scout pushes one notice into the session; with no socket or a session that would hold pushes, the SessionStart and Stop hooks say so and tell the lemon to run the background waiter. `watch --self --status` reports the socket, setting, scout and path.
