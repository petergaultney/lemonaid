# Patch

#### Fixed

- **Brief views hide done children and archived children whose working directory is gone.** Archived children with an existing directory remain visible for cleanup. Redraws read brief status and inbox records without querying tmux or running place hooks; `brief children --all` still shows the complete list.
