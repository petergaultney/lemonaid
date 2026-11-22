# Patch

#### Changed

- **The grove window opens at once the first time.** Where a tmux key summons it, the inbox starts the window in its hidden session when the inbox opens, and the window loads the grove while it starts. A summon key that has to start the window shows it as soon as it's up rather than after a fixed 3 seconds; add its lines again with `lemonaid grove window binding` to get that.
