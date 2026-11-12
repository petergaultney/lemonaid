# Patch

#### Fixed

- **`lma` draws its toasts again.** `LemonaidApp._refresh_notifications`, which refreshes the inbox, had the name of Textual's private method that draws toasts and replaced it, so every `notify` in `lma` (undo hints, "Nothing to undo", patch results and the rest) was recorded but never shown. It is now `_refresh_inbox`.
