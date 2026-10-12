"""A Lua module that WezTerm's config requires to turn vault paths into clickable links.

Lemonaid owns the whole module file and rewrites it on every install, so the
user's `wezterm.lua` only needs the lines in `REQUIRE`, added once by hand.
A hyperlink rule can only produce a URL, so the rule builds a private
`lemonaid-vault:` one and the module's `open-uri` handler passes the path on to
`lemonaid terminal open-vault`, which builds the Obsidian URL.
"""

from pathlib import Path

MODULE = "lemonaid_vault_links"
REQUIRE = f"""\
local ok, vault_links = pcall(require, '{MODULE}')
if ok then
  vault_links.apply(config)
elseif not vault_links:find("module '{MODULE}' not found", 1, true) then
  wezterm.log_error(vault_links)
end
"""


def _long_string(text: str) -> str:
    level = next(n for n in range(len(text) + 1) if f"]{'=' * n}]" not in text)
    return f"[{'=' * level}[{text}]{'=' * level}]"


def module_text(regex: str, lemonaid: str) -> str:
    return f"""\
-- Written by `lemonaid terminal vault-links wezterm`; rewritten on every install.
local wezterm = require 'wezterm'

local LEMONAID = {_long_string(lemonaid)}
local PREFIX = 'lemonaid-vault:'

wezterm.on('open-uri', function(window, pane, uri)
  if uri:sub(1, #PREFIX) ~= PREFIX then
    return
  end
  local cwd = pane:get_current_working_dir()
  local dir = cwd and (cwd.file_path or tostring(cwd))
  wezterm.background_child_process(
    dir and {{ LEMONAID, 'terminal', 'open-vault', '--cwd', dir, '--', uri:sub(#PREFIX + 1) }}
      or {{ LEMONAID, 'terminal', 'open-vault', '--', uri:sub(#PREFIX + 1) }}
  )
  return false
end)

local M = {{}}

function M.apply(config)
  config.hyperlink_rules = config.hyperlink_rules or wezterm.default_hyperlink_rules()
  table.insert(config.hyperlink_rules, {{
    regex = {_long_string(regex)},
    format = PREFIX .. '$0',
  }})
end

return M
"""


def module_path(config_dir: Path) -> Path:
    return config_dir / f"{MODULE}.lua"


def requires_module(config_dir: Path) -> bool:
    """Whether the user's `wezterm.lua` in *config_dir* already requires the module."""
    config = config_dir / "wezterm.lua"
    return config.exists() and MODULE in config.read_text()
