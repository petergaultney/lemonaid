# Patch

The scratch inbox no longer shows a stale answer about whether its pane has the keyboard. Every check asks tmux at a different moment, and one that asked earlier but answered last used to win. Clicking the lemon beside the inbox could then jump to it instead of keeping the inbox focused, and the unfocused dim could flip back the wrong way.

Quitting the inbox about ten seconds after it opened no longer fails with "No nodes match 'Footer'". That is when the timer that hides the key hints fires.
