# Patch

#### Fixed

- **The grove's stream and roads run to the map's edge, and blocks keep a gap from them.** The stream stopped at the default world's border when blocks made the map larger, and blocks could sit right against a road or the stream. Blocks already placed are trimmed or moved the next time the grove opens.
