# Minor

#### Added

- **The web grove opens a lemon's own page.** Jumping to a lemon in `lemonaid grove serve` shows its brief beside its conversation, read from the harness's transcript or OpenClaw's `chat.history`, with a box that sends what you type through the lemon's front end as your own words: its tmux or WezTerm pane, or OpenClaw's `chat.send`. A cmux lemon gets mail instead. See [grove.md](docs/grove.md#the-grove-in-a-browser).
- **An OpenClaw lemon can be prompted.** The chat front end's prompt sends the text with `chat.send`, so a lemon whose scout can't take mail is woken in its session as other front ends wake theirs.
