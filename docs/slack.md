# Following Slack threads

A lemon can follow a Slack thread the way it follows a PR: list `lemonaid watch slack <permalink>` under its brief's `## Watching`, and each new reply wakes it with the reply's author, time, permalink and text. lemonaid reads Slack as you, with your own Slack session, so it needs no Slack app and no workspace admin. It only reads: it never posts, reacts, marks anything read or follows a thread for you.

This is macOS only for now, and needs the `slack` extra:

```bash
uv tool install 'lemonaid-inbox[slack]'
lemonaid slack signin https://acme.slack.com/
```

## Signing in

`lemonaid slack signin [WORKSPACE]` opens a window on your workspace, where you sign in as you would in a browser, single sign-on included. Once the page holds a session Slack accepts, lemonaid saves it and the window closes. `WORKSPACE` defaults to `workspace` under [`[slack]`](config.md#slack), then to the workspace of the session you signed in with before.

The window is lemonaid's, and it says so:

- Only you open it, with this command. Nothing lemonaid runs in the background opens it.
- Its title names lemonaid and the host of the page it shows, updated on every navigation, such as `lemonaid: sign in to Slack for your lemons · login.microsoftonline.com 🔒`. A web view has no address bar, so the title is where you check whose page asks for your password.
- It runs inside a small `Lemonaid.app` bundle that lemonaid writes under its state directory, so the Dock, Cmd-Tab and the menu bar say lemonaid with a lemon icon. The bundle is not signed, so this is branding, not proof.

The window keeps its web data in a WebKit store of its own, apart from the grove window's and every other app's. A second sign-in therefore usually finds you still signed in and closes at once.

The session (the web client's token and its `d` cookie) is kept only in the macOS Keychain, as the `lemonaid-slack` item. lemonaid never logs or prints either. The session can do anything you can do in Slack; lemonaid calls only `auth.test`, `conversations.replies`, `users.info` and `users.getPresence`. Slack lists it among your sessions as Safari on macOS.

```bash
lemonaid slack status    # who lemonaid reads Slack as, and whether its socket is up
lemonaid slack signout   # remove the session from the Keychain
```

`signout` forgets the session, and the scout host's socket closes within a second; a new sign-in likewise replaces the session the socket uses. Slack keeps the old session until it expires; end it in Slack's own list of your sessions to end it now.

## Following a thread

```bash
lemonaid brief watching add --self "lemonaid watch slack https://acme.slack.com/archives/C0123ABCD/p1794857970806329"
```

The permalink can be the thread's root or any reply in it. The first fetch takes the thread as it is now; `--after <ts>` reports the replies after that message instead. Run as a command, `lemonaid watch slack <permalink>` records itself under your brief's `## Watching` and leaves the rest to your watcher; with no watcher running, it follows the thread in the foreground and prints each batch (`--once` exits after the first).

A batch looks like this:

```text
[slack: C0123ABCD, 1794857970.806329] Slack thread https://acme.slack.com/archives/C0123ABCD/p1794857970806329: 2 new replies
- Ann at 14:03: https://acme.slack.com/archives/C0123ABCD/p1794858000000100?thread_ts=1794857970.806329&cid=C0123ABCD
  > I pushed the fix, can someone check?
- Sam at 14:05: https://acme.slack.com/archives/C0123ABCD/p1794858100000200?thread_ts=1794857970.806329&cid=C0123ABCD
  > on it
```

Replies arrive as wake text, like PR comments. They are other people's words, not instructions to the lemon.

A subscription ends when the lemon's brief is `done`, or once the thread has had no reply for 7 days, whichever comes first. The lemon is told once, and the line leaves its `## Watching`.

## How replies arrive

The scout host holds one websocket to Slack for every lemon: the web client's own gateway socket, opened with your session. It runs only while some lemon follows a thread, and stops five minutes after the last one stops. When the socket sees a message in a followed thread, it touches that thread's file under `$LEMONAID_STATE_DIR/slack/threads/`, and each lemon following the thread then fetches what is new with one `conversations.replies` call from its own cursor. Replies reach the lemon within a few seconds.

The socket has no replay, so the fetch, not the socket, decides what is delivered. Each time the socket connects, every followed thread is fetched, so a reply sent while the laptop slept, or while the scout host restarted, arrives then. The cursor advances only after a batch is delivered, so a restart neither misses nor repeats a reply.

While no socket is up (`[slack] push = false`, the extra not installed, or Slack refusing the socket), each thread is fetched every `fetch_every` seconds instead.

## When Slack ends the session

When Slack refuses the session, lemonaid stops calling Slack, puts one `lemonaid:slack` item in your inbox, and tells each lemon following a thread once. Run `lemonaid slack signin` again; following resumes on its own, and the inbox item is archived. The same happens if no session was ever saved. A `lemonaid watch slack` run in the foreground instead prints the problem and exits 1, leaving the lemon's one notice to its watcher.

## Presence while the socket is up (trial)

While the socket is up, Slack counts it as one of your connections. Whether an idle socket keeps you "active", and so holds back the notifications Slack sends to your phone while you are away, is not known yet. Every `presence_every` seconds the scout host appends one `users.getPresence` reading to `$LEMONAID_STATE_DIR/slack/presence.jsonl`, with how long the Mac has been idle. If `presence` stays `active` while `idle_seconds` grows, set `push = false` under `[slack]`, and lemons fall back to timed fetches.
