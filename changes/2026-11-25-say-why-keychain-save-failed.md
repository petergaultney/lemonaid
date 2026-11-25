# Patch

`lemonaid slack signin` says why a Keychain save failed: a locked login keychain or no GUI session names the `security unlock-keychain` fix, and any other failure shows `security`'s exit status and message. The sign-in window reports it as one line instead of a traceback.

The sign-in window also says, once per change, what it is waiting on (no web token on the page, no `d` cookie, or why Slack rejected the token), and its closing line names the last of these.
