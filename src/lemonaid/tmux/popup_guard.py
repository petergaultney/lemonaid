"""Keep a fast popup's client on its own session.

A tmux key pressed while a popup has focus acts for the popup's own client, the `tmux attach`
running inside it. One that switches session, such as `choose-tree` or a choice in the scratch
inbox, would leave the popup showing that session, keys and all, until the popup is detached.
These hooks give the switch to the client the popup was opened over instead, and close the
popup.

The popup's client is the one that attached to the popup's session last, known by its name and
process together: names are ttys, which a later terminal may reuse.
"""

_INDEX = 110  # follow.py's hooks use 100


def hooks(session: str, opener_option: str) -> dict[str, str]:
    """`set-hook -g` names and commands for the popup on *session*, whose opener's client name
    is in *session*'s *opener_option*.
    """
    inner = f"@lemonaid_inner{session}"
    client = "#{client_name}:#{client_pid}"
    ours = f"#{{==:{client},#{{{inner}}}}}"
    away = "#{!:#{m:_lma_*,#{session_name}}}"
    opener = f"$(tmux show-options -t ={session}: -qv {opener_option})"
    move = f'tmux switch-client -c \\"{opener}\\" -t #{{pane_id}}'
    return {
        f"client-attached[{_INDEX}]": (
            f'if-shell -F "#{{==:#{{session_name}},{session}}}" '
            f'{{ set-option -gF {inner} "{client}" }}'
        ),
        f"client-session-changed[{_INDEX}]": (
            f'if-shell -F "#{{&&:{ours},{away}}}" {{ run-shell -b "{move}" ; detach-client }}'
        ),
    }
