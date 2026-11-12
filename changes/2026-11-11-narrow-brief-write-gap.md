# Patch

#### Fixed

- **A brief edit no longer loses a save made while its new text is being written.** The check for a concurrent save now comes after the temp file is written, just before the rename.
