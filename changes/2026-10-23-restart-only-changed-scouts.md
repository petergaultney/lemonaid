# Patch

#### Changed

- **A new install restarts only the watchers whose code it changed, and only its own.** Each `watch --self` waiter records a digest of the lemonaid modules it loaded and the install it runs from; the first command of a new version signals a waiter only when that code differs on disk. A lemonaid run from a dev checkout no longer signals the installed tool's waiters, and commands starting together after an install send one signal per waiter instead of one each.
