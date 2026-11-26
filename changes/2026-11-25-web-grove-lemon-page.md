# Minor

#### Added

- **The web grove opens a lemon's own page.** Jumping to a lemon in `lemonaid grove serve` shows its brief beside its conversation, read from the harness's transcript or OpenClaw's `chat.history`, with a box that sends what you type through the lemon's front end as your own words: its tmux or WezTerm pane, or OpenClaw's `chat.send`. A cmux lemon gets mail instead. See [grove.md](docs/grove.md#the-grove-in-a-browser).
- **An OpenClaw lemon can be prompted.** The chat front end's prompt sends the text with `chat.send`, so a lemon whose scout can't take mail is woken in its session as other front ends wake theirs.
- **The web grove has a prefix key.** Backtick twice goes back to the grove from any page, a text box included, and from the grove back to the last lemon, as closing the grove with Backspace or Escape does; backtick, then `b`, focuses a lemon's brief; backtick, then `h`, types a backtick. `[web]` in the config changes them.
- **An OpenClaw lemon's page is quick.** With the new `openclaw` extra, `grove serve` reads and sends over one held gateway connection instead of an `openclaw` process per call, and the page shows the brief without waiting for the conversation.
- **The web grove logs what browsers did,** to `logs/web-grove.jsonl` in lemonaid's state directory: each page's screen, errors, keys and touches, and the calls that failed, ran slow or changed something, never what was typed to a lemon.
