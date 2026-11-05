# Patch

A pushed watch batch carries each new Relay comment and PR comment in full, one block per comment with its author and line breaks, instead of its first 100 characters. A comment is cut at 4000 characters and a whole batch at 30000, each with a pointer back to the source. Doc body edits show up to 20 hunks of 8000 characters each (was 5 of 500).

The pushed instruction no longer tells a lemon to read the changed sources first; it says comments are included and to fetch one only where a cut marks it as omitted.
