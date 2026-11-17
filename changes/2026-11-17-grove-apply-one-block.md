# Minor

`lemonaid grove apply FILE --block N` applies only one block's plot and trees from a proposed layout, checked against where the other blocks are now, so other groups moving since `propose` can't be overwritten.

`lemonaid grove show` now defaults to the size the grove screen last had, `show N --compact` prints a line per tree with its list position, `show --json` gives each tree's zoomed crown center and list position, and the `list-away` warning now says whether each tree stands on its list, and which way it is off when it doesn't.
