# Patch

- The inbox no longer redraws every row three times a second while nothing changes, and it samples the scratch pane's size with `tmux` only while a resize settles (every 2 s otherwise, instead of 4 times a second).
- The inbox's watcher reuses its process listing while every lemon in it still runs, rather than running `ps -A` every 2 s.
