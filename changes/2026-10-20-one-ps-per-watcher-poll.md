# Patch

#### Fixed

- **The inbox's watcher lists processes once per poll** instead of running `ps` on each lemon's terminal. With 120 live lemons it had been starting about 20 processes a second, most of the inbox's CPU.
