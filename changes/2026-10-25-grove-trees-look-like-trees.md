# Patch

#### Changed

- **The grove's trees look like trees.** A crown is a wide, rounded dome of leaf clumps lit from the upper left and flatter underneath than on top, arranged differently on every tree, over a short two-tone trunk, which thickens as the tree grows. Trees in a zoomed block grow no bigger than a grown tree unless `grove_big_trees = true`. Crowns are wider than before, so a saved grove spaces its trees again the next time it is laid out.
- **A done lemon on a crown is blue,** as its status is in the lemon list, instead of a pale leaf color.
- **Working lemons pulse smoothly.** The grove blends each frame from two pictures instead of drawing it again, and a grove waiting hidden shows its lemons at rest rather than stuck at their darkest.
- **A lemon list in a crowded block stays put while its neighbors change.** It used to jump whenever another tree's lemons came or went, if it could not avoid covering something.
