# Patch

#### Fixed

- **The idle-brief sweep no longer archives the brief of a live lemon or one waiting on you.** It skips a brief whose Status is `blocked`, `alert`, `merge`, `approve`, `review` or `running`, and one whose lemon's harness is still running even when its inbox row was archived. `brief revive` also finds a brief in the attic whose record still pointed at the briefs directory.
