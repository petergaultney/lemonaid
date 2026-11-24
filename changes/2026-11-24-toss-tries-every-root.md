# Patch

- **`place toss <key>` tries every configured root before giving up.** A root whose `path_of` hook failed used to refuse the toss without asking the roots after it. Now the toss is refused as "could not resolve" only when no root has the key and at least one root's check failed.
