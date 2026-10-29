# Patch

#### Changed

- **A lead stops tracking children whose sessions are archived.** `watch --self`, the brief view and the stop hook's children check no longer read an archived child's brief or probe its liveness, so a lead's cost stays with its live children rather than everyone it ever started. The parent link stays as the record: `lemon children` and `brief children --all` still list the child, and unarchiving it brings it back.
