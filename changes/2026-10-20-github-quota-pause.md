# Patch

#### Fixed

- **Watches stop spending GitHub quota once it runs out.** A read refused for quota, or one that leaves fewer than 100 points, pauses every GitHub watch on the machine until GitHub's reset, and each lemon is told once with the resume time instead of "Cannot reach GitHub".
- **A failing GitHub watch backs off.** Each failure in a row doubles the wait before that subscription's next read, up to 10 minutes.
