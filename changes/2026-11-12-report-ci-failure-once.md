# Patch

#### Fixed

- **`watch pr` reports a head's failed check once.** A scheduled check that kept failing on the same head woke the lemon on every new run; it now wakes again only for a new head, a different set of failed checks, or a failure after the checks had all finished without one.
