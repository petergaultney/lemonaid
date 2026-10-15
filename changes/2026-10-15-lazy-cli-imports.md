# Patch

#### Changed

- **Faster command startup on Python 3.15.** Commands that do not use the TUI or color parsing avoid loading Textual until needed. Python 3.11 to 3.14 keep their existing eager imports.
