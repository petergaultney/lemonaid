# Patch

#### Fixed

- **A tree dragged within its block stays where it's dropped.** A drop could be turned down after you let go, with "the grove would move it from there", in spots where the tree and its list plainly fit. A drag, a drop, `grove plant` and `grove apply` now judge a spot by one rule, so a spot that can't take the tree turns red while you drag and names the block edge or the tree in the way.
