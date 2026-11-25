-- The thread panel: every thread of the buffer you are in, beside it, in the order their
-- anchors appear, with orphans (threads whose anchor is gone) last.  A resolved thread is
-- one line.  Moving through the panel lights up the text a thread is about.  It follows
-- the buffer you are in, and stays on the last one with threads when you move elsewhere.
--
-- The panel is where you read: a comment is read when the cursor moves onto it here, and
-- an unread one has a dot before its author.  The unread filter shows only threads with a
-- comment you haven't read.  It is one switch for the whole nvim.  A thread you read while
-- it is on stays, so it doesn't vanish from under you; turning the filter off and on again
-- drops it.

local render = require("lma.render")
local state = require("lma.state")

local M = {}

local WIDTH = 50
local ns = vim.api.nvim_create_namespace("lma_panel")
local focus_ns = vim.api.nvim_create_namespace("lma_focus")

-- at: where the cursor was when the panel last counted a visit, or last redrew; nvim
-- reports a cursor event after a redraw that leaves the cursor put, which visits nothing
local panel = { buf = nil, win = nil, source = nil, rows = {}, at = nil }

-- unread_only: the filter is on; shown[buf]: the root ids of the threads it shows there,
-- every thread unread since the filter went on, read since or not
local filter = { unread_only = false, shown = {} }

-- expanded[buf][root]: threads drawn with their resolved comments, since one of those was
-- unread when drawn; kept after you read it, so what you are reading stays in view
local expanded = {}

-- Set by lma.init: the buffer-local keys (reply, resolve) a rendered buffer gets.
M.on_open = function(_) end
-- Set by lma.init: you are on `comment` of `source` in the panel, so you've read it.
M.on_visit = function(_, _) end

function M.is_open()
  return panel.win ~= nil and vim.api.nvim_win_is_valid(panel.win)
end

function M.source()
  return panel.source
end

local function one_line(text)
  return vim.trim((text:gsub("%s+", " ")))
end

local function anchored_text(buf, thread)
  local sr, sc, er, ec = state.anchor_range(buf, thread)
  if not sr then return "" end
  local ok, lines = pcall(vim.api.nvim_buf_get_text, buf, sr, sc, er, ec, {})
  if not ok then return "" end
  return one_line(table.concat(lines, " "))
end

-- The threads of `source` the panel shows: all of them, or with the filter on, those in
-- its set, which takes in every thread unread now.
local function shown_threads(source, threads)
  if not filter.unread_only then return threads end
  local shown = filter.shown[source] or {}
  filter.shown[source] = shown
  for _, thread in ipairs(threads) do
    if state.thread_unread(source, thread) then shown[thread.root.id] = true end
  end
  return vim.tbl_filter(function(thread) return shown[thread.root.id] == true end, threads)
end

-- What a row shows: the thread, the comment and where in its body, as one string.
local function row_key(info)
  if not info then return nil end
  return ("%s/%s/%s"):format(info.thread.root.id, info.comment and info.comment.id or "", info.body_start or "")
end

-- After a redraw, puts the cursor back on what it was on, which rows added above it would
-- otherwise change under it: the same line of the same comment, or else the same thread.
local function keep_cursor_on(before, cursor)
  local wanted = row_key(before)
  if not wanted or row_key(panel.rows[cursor[1]]) == wanted then return end
  local thread_row
  for row = 1, vim.api.nvim_buf_line_count(panel.buf) do
    local info = panel.rows[row]
    if row_key(info) == wanted then
      vim.api.nvim_win_set_cursor(panel.win, { row, cursor[2] })
      return
    end
    if info and info.thread.root.id == before.thread.root.id then thread_row = thread_row or row end
  end
  if thread_row then vim.api.nvim_win_set_cursor(panel.win, { thread_row, 0 }) end
end

function M.draw()
  local st = state.get(panel.source)
  if not M.is_open() then return end
  local out = render.new()
  local function add(text, info)
    out.lines[#out.lines + 1] = text
    out.rows[#out.lines] = info
    return #out.lines - 1
  end
  local all = st and st.threads or {}
  local threads = shown_threads(panel.source, all)
  if filter.unread_only then
    local header = #threads == 0 and ("No unread comments (%d threads)"):format(#all)
      or ("Unread only (%d of %d threads)"):format(#threads, #all)
    out.hls[#out.hls + 1] = { row = add(header, nil), col_start = 0, col_end = #header, group = "LmaUnread" }
    add("", nil)
  end
  expanded[panel.source] = expanded[panel.source] or {}
  local full = expanded[panel.source]
  local function unread(comment) return state.comment_unread(panel.source, comment.id) end
  for _, thread in ipairs(threads) do
    for _, comment in ipairs(thread.comments) do
      if comment.resolved and unread(comment) then full[thread.root.id] = true end
    end
    local sr = state.anchor_range(panel.source, thread)
    local label = sr and ("L%d"):format(sr + 1) or "orphaned"
    if thread.root.resolved and not full[thread.root.id] then
      local text = ("%s  ✓ %s: %s"):format(label, thread.root.author, one_line(thread.root.body))
      local row = add(text, { thread = thread, comment = thread.root })
      out.hls[#out.hls + 1] = { row = row, col_start = 0, col_end = #text, group = "LmaResolved" }
    else
      local text = label .. "  " .. anchored_text(panel.source, thread)
      local row = add(text, { thread = thread })
      out.hls[#out.hls + 1] = { row = row, col_start = 0, col_end = #label, group = "LineNr" }
      out.hls[#out.hls + 1] = { row = row, col_start = #label + 2, col_end = #text, group = "LmaAnchor" }
      render.thread(out, thread, 2, full[thread.root.id] == true, unread)
      add("", nil)
    end
  end
  if #out.lines == 0 then out.lines = { "No comments in this buffer." } end
  local cursor = vim.api.nvim_win_get_cursor(panel.win)
  local before = panel.rows[cursor[1]]
  render.write(panel.buf, ns, out)
  panel.rows = out.rows
  keep_cursor_on(before, cursor)
  panel.at = vim.api.nvim_win_get_cursor(panel.win)
end

local function source_win()
  local win = vim.fn.bufwinid(panel.source or -1)
  return win ~= -1 and win or nil
end

local function clear_focus()
  if panel.source and vim.api.nvim_buf_is_valid(panel.source) then
    vim.api.nvim_buf_clear_namespace(panel.source, focus_ns, 0, -1)
  end
end

function M.info_at_cursor()
  if not M.is_open() then return nil end
  return panel.rows[vim.api.nvim_win_get_cursor(panel.win)[1]]
end

local function focus_thread()
  clear_focus()
  local info = M.info_at_cursor()
  local cursor = vim.api.nvim_win_get_cursor(panel.win)
  local moved = not (panel.at and panel.at[1] == cursor[1] and panel.at[2] == cursor[2])
  panel.at = cursor
  if info and info.comment and moved then M.on_visit(panel.source, info.comment) end
  local sr, sc, er, ec
  if info then sr, sc, er, ec = state.anchor_range(panel.source, info.thread) end
  if not sr then return end
  local point = sr == er and sc == ec
  vim.api.nvim_buf_set_extmark(panel.source, focus_ns, sr, sc, point
    and { line_hl_group = "LmaFocus", priority = 4600 }
    or { end_row = er, end_col = ec, hl_group = "LmaFocus", priority = 4600 })
  local win = source_win()
  if not win then return end
  vim.api.nvim_win_call(win, function()
    if sr + 1 < vim.fn.line("w0") or er + 1 > vim.fn.line("w$") then
      vim.fn.winrestview({ topline = math.max(1, sr + 1 - math.floor(vim.api.nvim_win_get_height(0) / 3)) })
    end
  end)
end

local function jump()
  local info = M.info_at_cursor()
  local win = source_win()
  if not (info and win) then return end
  local sr, sc = state.anchor_range(panel.source, info.thread)
  if not sr then return end
  vim.api.nvim_set_current_win(win)
  vim.api.nvim_win_set_cursor(win, { sr + 1, sc })
end

function M.close()
  if M.is_open() then vim.api.nvim_win_close(panel.win, true) end
end

local function open(source)
  local return_to = vim.api.nvim_get_current_win()
  vim.cmd(("botright vertical %dnew"):format(WIDTH))
  panel.win, panel.buf, panel.source = vim.api.nvim_get_current_win(), vim.api.nvim_get_current_buf(), source
  vim.bo[panel.buf].buftype = "nofile"
  vim.bo[panel.buf].bufhidden = "wipe"
  vim.bo[panel.buf].swapfile = false
  vim.bo[panel.buf].filetype = "lmapanel"
  vim.api.nvim_buf_set_name(panel.buf, "lma://threads")
  for option, value in pairs({
    wrap = true, linebreak = true, breakindent = true, breakindentopt = "shift:2",
    number = false, relativenumber = false, signcolumn = "no", winfixwidth = true,
    cursorline = true, list = false,
  }) do
    vim.wo[panel.win][option] = value
  end
  vim.keymap.set("n", "<cr>", jump, { buffer = panel.buf, desc = "lma: jump to this thread" })
  vim.keymap.set("n", "q", M.close, { buffer = panel.buf, desc = "lma: close the panel" })
  M.on_open(panel.buf)

  local group = vim.api.nvim_create_augroup("lma_panel", { clear = true })
  vim.api.nvim_create_autocmd("CursorMoved", { group = group, buffer = panel.buf, callback = focus_thread })
  vim.api.nvim_create_autocmd("BufLeave", { group = group, buffer = panel.buf, callback = clear_focus })
  vim.api.nvim_create_autocmd("BufWipeout", {
    group = group, buffer = panel.buf,
    callback = function()
      clear_focus()
      panel.buf, panel.win, panel.rows = nil, nil, {}
      expanded = {}
    end,
  })
  M.draw()
  vim.api.nvim_set_current_win(return_to)
end

function M.toggle(source)
  if M.is_open() then M.close() else open(source) end
end

-- Turns the filter on or off, and opens the panel if it is closed.
function M.toggle_unread(source)
  filter.unread_only, filter.shown = not filter.unread_only, {}
  if M.is_open() then M.draw() else open(source) end
end

function M.unread_only()
  return filter.unread_only
end

-- The first row of each comment the panel shows that you haven't read, in order.
local function unread_rows()
  local rows, seen_ids = {}, {}
  for row = 1, vim.api.nvim_buf_line_count(panel.buf) do
    local info = panel.rows[row]
    local comment = info and info.comment
    if comment and not seen_ids[comment.id] then
      seen_ids[comment.id] = true
      if state.comment_unread(panel.source, comment.id) then rows[#rows + 1] = row end
    end
  end
  return rows
end

-- The row of `thread`'s first unread comment, else of its first line; nil when the panel
-- doesn't show it.
local function row_of(thread)
  for _, row in ipairs(unread_rows()) do
    if panel.rows[row].thread.root.id == thread.root.id then return row end
  end
  for row = 1, vim.api.nvim_buf_line_count(panel.buf) do
    local info = panel.rows[row]
    if info and info.thread.root.id == thread.root.id then return row end
  end
end

-- Moves the cursor to `row` and reads the comment there, if any, even when the cursor is
-- on it already (the cursor event, if any, finds the move counted).
local function land(row)
  vim.api.nvim_win_set_cursor(panel.win, { row, 0 })
  panel.at = { row, 0 }
  local info = panel.rows[row]
  if info and info.comment then M.on_visit(panel.source, info.comment) end
end

-- Moves into the panel, onto `thread`'s first unread comment or else its first line,
-- opening the panel if it is closed.  The filter, if on, takes the thread in, since you
-- asked for it.
function M.show_thread(source, thread)
  if not M.is_open() then open(source) end
  if panel.source ~= source then
    clear_focus()
    panel.source = source
  end
  if filter.unread_only then
    filter.shown[source] = filter.shown[source] or {}
    filter.shown[source][thread.root.id] = true
  end
  M.draw()
  local row = row_of(thread)
  if not row then return end
  vim.api.nvim_set_current_win(panel.win)
  land(row)
  vim.api.nvim_win_call(panel.win, function() vim.cmd("normal! zz") end)
end

-- Moves to the next (`step` 1) or previous (-1) unread comment from the cursor, wrapping
-- around, and reads it.  False when the panel shows none.
function M.visit_unread(step)
  if not M.is_open() then return false end
  local rows = unread_rows()
  if #rows == 0 then return false end
  local here = vim.api.nvim_win_get_cursor(panel.win)[1]
  local target
  if step > 0 then
    for _, row in ipairs(rows) do if row > here then target = row break end end
    target = target or rows[1]
  else
    for i = #rows, 1, -1 do if rows[i] < here then target = rows[i] break end end
    target = target or rows[#rows]
  end
  land(target)
  return true
end

-- The panel follows you to another buffer with threads.
function M.follow(buf)
  if M.is_open() and panel.source ~= buf and state.get(buf) then
    clear_focus()
    panel.source = buf
    M.draw()
  end
end

-- What a reply or resolve in the panel acts on.
function M.context()
  return panel.source, panel.rows
end

return M
