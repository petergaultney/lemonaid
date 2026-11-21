-- The thread panel: every thread of the buffer you are in, beside it, in the order their
-- anchors appear, with orphans (threads whose anchor is gone) last.  A resolved thread is
-- one line.  Moving through the panel lights up the text a thread is about.  It follows
-- the buffer you are in, and stays on the last one with threads when you move elsewhere.

local render = require("lma.render")
local state = require("lma.state")

local M = {}

local WIDTH = 50
local ns = vim.api.nvim_create_namespace("lma_panel")
local focus_ns = vim.api.nvim_create_namespace("lma_focus")

local panel = { buf = nil, win = nil, source = nil, rows = {} }

-- Set by lma.init: the buffer-local keys (reply, resolve) a rendered buffer gets.
M.on_open = function(_) end

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

function M.draw()
  local st = state.get(panel.source)
  if not M.is_open() then return end
  local out = render.new()
  local function add(text, info)
    out.lines[#out.lines + 1] = text
    out.rows[#out.lines] = info
    return #out.lines - 1
  end
  for _, thread in ipairs(st and st.threads or {}) do
    local sr = state.anchor_range(panel.source, thread)
    local label = sr and ("L%d"):format(sr + 1) or "orphaned"
    if thread.root.resolved then
      local text = ("%s  ✓ %s: %s"):format(label, thread.root.author, one_line(thread.root.body))
      local row = add(text, { thread = thread, comment = thread.root })
      out.hls[#out.hls + 1] = { row = row, col_start = 0, col_end = #text, group = "LmaResolved" }
    else
      local text = label .. "  " .. anchored_text(panel.source, thread)
      local row = add(text, { thread = thread })
      out.hls[#out.hls + 1] = { row = row, col_start = 0, col_end = #label, group = "LineNr" }
      out.hls[#out.hls + 1] = { row = row, col_start = #label + 2, col_end = #text, group = "LmaAnchor" }
      render.thread(out, thread, 2, false)
      add("", nil)
    end
  end
  if #out.lines == 0 then out.lines = { "No comments in this buffer." } end
  render.write(panel.buf, ns, out)
  panel.rows = out.rows
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
    end,
  })
  M.draw()
  vim.api.nvim_set_current_win(return_to)
end

function M.toggle(source)
  if M.is_open() then M.close() else open(source) end
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
