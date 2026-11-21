# Minor

#### Added

- **A lemon can follow a Slack thread or channel (macOS).** `lemonaid watch slack <link>` under a brief's `## Watching` wakes the lemon with each new message's author, time, permalink and text, until the brief is `done` or nothing has been posted for 7 days. `--match <regex>` wakes it only for messages whose text matches. It reads Slack as you, with the session `lemonaid slack signin` keeps in the Keychain, and never writes to Slack. It needs the `slack` extra: `uv tool install 'lemonaid-inbox[slack]'`.
- **`lemonaid slack signin` opens a sign-in window that names lemonaid and the page's host in its title,** inside a small `Lemonaid.app` so the Dock says lemonaid. `lemonaid slack status` says who lemonaid reads Slack as, and `slack signout` removes the session.
- **The scout host holds one Slack socket for every lemon,** and logs your Slack presence while it is up, to find out whether an idle socket keeps you active; `[slack] push = false` fetches on a timer instead.
