import datetime

from lemonaid.brief import frontmatter_edit

DEFAULTS = frontmatter_edit.Defaults(datetime.date(2026, 10, 21), ("Sam Smith",))

LEGACY = """\
# Task

Brief-ID: task.SkullHen

type: Brief

created: { at: 2026-10-21T10:00:00-04:00, by: BlessBar }

Parent: hq.LemonAce (play), 2026-10-21

Groups: lemonaid, misc

Hidden: yes

## Now

- Starting.
"""
