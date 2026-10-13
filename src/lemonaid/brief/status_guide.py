"""What `lemonaid brief status --help` tells a lemon about choosing a status."""

GUIDE = """\
Choose by whose move it is. Leave the status out when the next move is a lemon's or CI's;
the inbox then shows whether you are active, idle, deaf or dead. `review` is the one case
where the next move is a teammate's.

  blocked   the user can act now: a decision, an answer, something to review or try
  alert     the user's move is needed and harm grows while it waits (prod broken, spend
            running, data at risk); keep it rare
  review    the next move is a teammate's approving review, not the user's
  approve   you reviewed a teammate's PR and recommend the user approve it; a review of a
            lemon's PR sets no status while the PR waits on its author or merge
  merge     only the user's merge remains: the PR is approved, CI is green, it has no
            conflicts and it is out of draft; check `gh pr view <n> --json mergeable`
  running   nobody's move; you are minding a long pipeline or process, named under
            `### Running` in `## Now` (your own test suite is not one)
  done      nothing is left: the PR is merged or closed, or the output accepted, and no
            waiter runs; an open PR is never done

Several lemons waiting on the same move from the user: only the one that owns it is
`blocked` (or `merge`); the others set no status and name it under `### Waiting on`.
Put the reason in `## Now`, never on the `Status:` line. See docs/brief-status.md.
"""
