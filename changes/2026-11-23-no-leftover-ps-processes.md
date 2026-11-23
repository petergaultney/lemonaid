# Patch

#### Fixed

- **The scout host no longer keeps finished `ps` and `gh` processes as zombies.** A restart replaced its code while scouts still had those running, and nothing in the new code collected them; it now does as it starts.
