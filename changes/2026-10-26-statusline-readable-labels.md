# Patch

#### Fixed

- **The Claude statusline's model and session name are readable.** They were drawn with the faint attribute, which many dark themes render nearly invisible; they now use mid-gray. `label_color` under `[claude.statusline]` sets a 0-255 color, `"default"` or `"dim"`.
