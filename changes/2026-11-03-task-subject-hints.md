# Patch

#### Added

- **A task's URL and its holder's brief hint at each other.** Setting a task's PR or file URL prints the `brief pr add` or `brief doc add` command when the holder's brief doesn't watch it, and adding a PR or document to a brief prints the `task set-url` command for its tasks with no URL. A task's URL may now be an absolute file path, stored as its `file://` URL.
