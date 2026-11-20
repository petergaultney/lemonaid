-- The visual selection, the way nvim chose it, as 0-based (row, byte col) of its start and
-- exclusive end.  Call it from a mapping run in visual mode; it leaves visual mode.

local M = {}

-- Whether the selection ends with a line break that getregionpos() leaves out: the 0-based
-- row whose start is just past that break, or nil.  A yank keeps the break: in
-- 'selection' inclusive when the end sits past its line's last character (`$`, or an
-- empty line); in exclusive when the end sits on the first column of a later line, or
-- when the selection is one position past its line's last character (on an empty line,
-- the one character selected is the break).
local function line_break_end(v, cursor)
  local start, finish = v, cursor
  if cursor[2] < v[2] or (cursor[2] == v[2] and cursor[3] < v[3]) then start, finish = cursor, v end
  local row, col = finish[2], finish[3] -- 1-based
  if vim.o.selection == "exclusive" then
    if col == 1 and row > start[2] then return row - 1 end
    local one_position = start[2] == row and start[3] == col
    if one_position and col > #vim.fn.getline(row) then return row end
  elseif col > #vim.fn.getline(row) then
    return row
  end
  return nil
end

-- nil after saying why, for a blockwise selection, or a characterwise one with
-- 'selection' old.  nvim's getregionpos() decides what
-- is selected, so 'selection' and its exceptions (a one-character exclusive selection
-- holds that character) are nvim's rules, except for a selected final line break, which
-- it leaves out and a yank keeps (line_break_end).
function M.take(buf)
  local mode = vim.fn.mode()
  if mode == "v" and vim.o.selection == "old" then
    -- what a yank takes then depends on where the selection starts, in ways we don't follow
    vim.cmd("normal! \27")
    vim.notify("lma: with 'selection' old, select whole lines with V", vim.log.levels.WARN)
    return nil
  end
  local v, cursor = vim.fn.getpos("v"), vim.fn.getpos(".")
  local regions = vim.fn.getregionpos(v, cursor, { type = mode })
  local break_row = mode == "v" and line_break_end(v, cursor) or nil
  vim.cmd("normal! \27")
  if mode == "\22" then
    vim.notify("lma: a block selection can't be used; use v or V", vim.log.levels.WARN)
    return nil
  end
  -- each region is one line's [start, end]: 1-based rows, and 1-based columns of the
  -- first byte and of the last byte of the last character
  local first, last = regions[1][1], regions[#regions][2]
  local sr = first[2] - 1
  local start_line = vim.api.nvim_buf_get_lines(buf, sr, sr + 1, true)[1]
  local sc = math.min(first[3] - 1, #start_line)
  local line_count = vim.api.nvim_buf_line_count(buf)
  if break_row and break_row < line_count then return sr, sc, break_row, 0 end
  local er = last[2] - 1
  local end_line = vim.api.nvim_buf_get_lines(buf, er, er + 1, true)[1]
  return sr, sc, er, math.min(last[3], #end_line)
end

function M.is_visual()
  local mode = vim.fn.mode()
  return mode == "v" or mode == "V" or mode == "\22"
end

return M
