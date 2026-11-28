# Minor

#### Changed

- **Removing a Needs bullet removes the Questions entry that explained it.** The edit says so, where it used to be refused. A refusal for a Questions entry without a bullet now says how to fix it.
- **`brief now`'s refusal to drop a sub-heading says how to keep it:** include the heading and its bullets in the new body.

#### Added

- **An OpenClaw lemon finds itself by `OPENCLAW_SESSION_KEY`.** A gateway that passes the session key in each command's environment needs no `lemonaid openclaw register`, whatever model runtime the session uses.
- **`lemon end` ends an OpenClaw lemon.** It stops the session's doc watches and archives the session in OpenClaw, keeping the transcript, where it used to fail asking for a tmux socket.
