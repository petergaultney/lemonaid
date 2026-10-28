# Patch

#### Fixed

- **A lead's brief view no longer keeps the inbox busy.** Each refresh read and parsed every child's brief, including archived children it then hid, so a lead with a few hundred children held the inbox near 100% CPU. A refresh now skips archived children and re-reads only the child briefs that changed.
