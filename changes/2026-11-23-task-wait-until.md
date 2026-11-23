# Minor

#### Added

- **`lemonaid task wait-until TASK_ID TIME --reason TEXT`** tells the task inspector that the holder waits for a set time, such as a launch window or a cooldown, and it doesn't challenge the lemon as idle until then. The idle challenge offers it, and the `running` Status now says a timer you set isn't a process you mind.
