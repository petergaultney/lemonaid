-- Each buffer's threads, as the server last sent them in `lemonaid/threads`, and the
-- marks that draw them.  The server sends threads only when the comments change, not
-- when text moves, so we place an extmark at each anchor when they arrive and let nvim
-- carry it as you edit.
--
-- A thread is { anchor = LSP range or nil, comments = { ... }, root, mark }: `comments`
-- in tree order, each with its `depth`; `root` the first; `mark` the anchor's extmark id.

local M = {}

M.ns = vim.api.nvim_create_namespace("lma")
local conceal_ns = vim.api.nvim_create_namespace("lma_conceal")
-- a plain mark on each of the threads' own markers, to tell where they are now
local marker_ns = vim.api.nvim_create_namespace("lma_markers")

local HINT_LENGTH = 60

-- by_buf[buf] = { threads, encoding }
local by_buf = {}

-- Show the markers as written, for editing near them.
M.show_markers = false

-- Defaults only: a colorscheme that sets these groups wins.  Run again on ColorScheme,
-- because :hi clear drops them.
local function define_default_highlights()
  local set = function(name, link) vim.api.nvim_set_hl(0, name, { link = link, default = true }) end
  set("LmaAnchor", "LspReferenceText") -- the text a thread is about
  set("LmaSign", "DiagnosticHint")
  set("LmaHint", "Comment") -- the thread's first line, after the anchor's line
  set("LmaAuthor", "Title")
  set("LmaTime", "NonText")
  set("LmaQuote", "Comment") -- the part of its parent a reply is about
  set("LmaSpan", "LspReferenceText") -- that part, lit up in the parent
  set("LmaResolved", "NonText")
  set("LmaFocus", "IncSearch") -- the thread under the panel's cursor
end

define_default_highlights()
vim.api.nvim_create_autocmd("ColorScheme", {
  group = vim.api.nvim_create_augroup("lma_colors", { clear = true }),
  callback = define_default_highlights,
})

function M.get(buf)
  return by_buf[buf]
end

function M.forget(buf)
  by_buf[buf] = nil
  if vim.api.nvim_buf_is_valid(buf) then
    vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
    vim.api.nvim_buf_clear_namespace(buf, conceal_ns, 0, -1)
    vim.api.nvim_buf_clear_namespace(buf, marker_ns, 0, -1)
  end
end

local function line(buf, row)
  return vim.api.nvim_buf_get_lines(buf, row, row + 1, false)[1] or ""
end

-- An LSP position as a 0-based row and byte column in the buffer.
function M.to_byte(buf, position, encoding)
  local row = position.line
  local text = line(buf, row)
  local ok, col = pcall(vim.str_byteindex, text, encoding, position.character, false)
  return row, ok and math.min(col, #text) or #text
end

-- A byte position as an LSP position.
function M.to_lsp(buf, row, col, encoding)
  local text = line(buf, row)
  return { line = row, character = vim.str_utfindex(text, encoding, math.min(col, #text), false) }
end

local function first_line(body)
  local text = body:match("^[^\n]*")
  return vim.fn.strchars(text) > HINT_LENGTH and vim.fn.strcharpart(text, 0, HINT_LENGTH - 1) .. "…" or text
end

local function draw_anchor(buf, thread, encoding)
  local sr, sc = M.to_byte(buf, thread.anchor.start, encoding)
  local er, ec = M.to_byte(buf, thread.anchor["end"], encoding)
  local resolved = thread.root.resolved
  local replies = #thread.comments - 1
  local hint = ("%s: %s%s"):format(thread.root.author, first_line(thread.root.body),
    replies > 0 and (" (+%d)"):format(replies) or "")
  local mark = {
    end_row = er, end_col = ec,
    hl_group = not resolved and "LmaAnchor" or nil,
    sign_text = resolved and "✓" or "┃",
    sign_hl_group = resolved and "LmaResolved" or "LmaSign",
    virt_text = not resolved and { { "  " .. hint, "LmaHint" } } or nil,
    virt_text_pos = "eol",
    right_gravity = false, end_right_gravity = true,
    priority = 4500,
  }
  local ok, id = pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, sr, sc, mark)
  thread.mark = ok and id or nil
end

-- The threads' own markers, hidden.  The server sends each thread's markers (`markers`):
-- the range of what removing one removes, and that text.  So text that only looks like
-- a marker (an example in a string, a reply's id) is never hidden, and neither is
-- anything where the buffer no longer holds the marker's text: a notification can
-- describe an older version of the buffer.  We keep a plain extmark on each marker and
-- hide it only while that text is still there, so a marker edited into code shows.  A
-- marker whose range is a whole line, line ending and all, hides as a line; one inside a
-- line (inline Markdown) hides in place.
local function place_markers(buf, st)
  vim.api.nvim_buf_clear_namespace(buf, marker_ns, 0, -1)
  st.markers = {}
  for _, thread in ipairs(st.threads) do
    for _, marker in ipairs(thread.markers or {}) do
      local sr, sc = M.to_byte(buf, marker.range.start, st.encoding)
      local er, ec = M.to_byte(buf, marker.range["end"], st.encoding)
      local expected = (marker.text:gsub("\r", ""))
      local ok, text = pcall(vim.api.nvim_buf_get_text, buf, sr, sc, er, ec, {})
      if ok and table.concat(text, "\n") == expected then
        local placed, id = pcall(vim.api.nvim_buf_set_extmark, buf, marker_ns, sr, sc, {
          end_row = er, end_col = ec,
          -- text typed just before or just after a marker stays outside it
          right_gravity = true, end_right_gravity = false,
        })
        if placed then
          st.markers[#st.markers + 1] = { id = id, whole_line = sc == 0 and ec == 0 and er == sr + 1, text = expected }
        end
      end
    end
  end
end

function M.refresh_conceal(buf)
  local st = by_buf[buf]
  if not (st and vim.api.nvim_buf_is_valid(buf)) then return end
  vim.api.nvim_buf_clear_namespace(buf, conceal_ns, 0, -1)
  if M.show_markers then return end
  for _, marker in ipairs(st.markers or {}) do
    local at = vim.api.nvim_buf_get_extmark_by_id(buf, marker_ns, marker.id, { details = true })
    if at[1] then
      local sr, sc, er, ec = at[1], at[2], at[3].end_row, at[3].end_col
      local ok, text = pcall(vim.api.nvim_buf_get_text, buf, sr, sc, er, ec, {})
      -- a whole-line marker must still be a whole line: text typed at its start sits
      -- inside the line, and hiding the line would hide that text
      local still_whole = not marker.whole_line or (sc == 0 and ec == 0 and er == sr + 1)
      if ok and still_whole and table.concat(text, "\n") == marker.text then
        local mark = marker.whole_line and { end_row = er - 1, conceal_lines = "" }
          or { end_row = er, end_col = ec, conceal = "" }
        pcall(vim.api.nvim_buf_set_extmark, buf, conceal_ns, sr, sc, mark)
      end
    end
  end
end

-- Concealing needs 'conceallevel' above 0 in the window.  Markdown windows are left to
-- render-markdown, which raises it while it draws, as critic.lua's delimiters are.
function M.allow_conceal(buf)
  if vim.bo[buf].filetype == "markdown" then return end
  for _, win in ipairs(vim.fn.win_findbuf(buf)) do
    if vim.wo[win].conceallevel == 0 then
      vim.api.nvim_set_option_value("conceallevel", 2, { scope = "local", win = win })
    end
  end
end

local RECHECK_DELAY_MS = 100

-- Edits can turn a marker into ordinary text; look again once they settle.
local function follow_edits(buf, st)
  if st.following then return end
  st.following, st.tick = true, 0
  vim.api.nvim_buf_attach(buf, false, {
    on_lines = function()
      local now = by_buf[buf]
      if not now then return true end
      now.tick = now.tick + 1
      local tick = now.tick
      vim.defer_fn(function()
        if by_buf[buf] == now and now.tick == tick then M.refresh_conceal(buf) end
      end, RECHECK_DELAY_MS)
    end,
    on_reload = function() end,
  })
end

-- JSON's null arrives as vim.NIL, which is truthy.
local function value(x)
  if x == vim.NIL then return nil end
  return x
end

function M.set(buf, threads, encoding)
  for _, thread in ipairs(threads) do
    thread.anchor = value(thread.anchor)
    for _, comment in ipairs(thread.comments) do
      comment.re, comment.span = value(comment.re), value(comment.span)
    end
    thread.root = thread.comments[1]
  end
  -- the server sorts anchored threads by position and puts orphans last
  local previous = by_buf[buf]
  local st = { threads = threads, encoding = encoding, following = previous and previous.following, tick = 0 }
  by_buf[buf] = st
  vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
  for _, thread in ipairs(threads) do
    if thread.anchor then draw_anchor(buf, thread, encoding) end
  end
  place_markers(buf, st)
  follow_edits(buf, st)
  M.refresh_conceal(buf)
  M.allow_conceal(buf)
end

-- Where a thread's anchor is now: 0-based start row and col, end row and col.
function M.anchor_range(buf, thread)
  if not thread.mark then return nil end
  local mark = vim.api.nvim_buf_get_extmark_by_id(buf, M.ns, thread.mark, { details = true })
  if not mark[1] then return nil end
  return mark[1], mark[2], mark[3].end_row or mark[1], mark[3].end_col or mark[2]
end

-- The innermost unresolved thread whose anchor holds the cursor, else the innermost
-- resolved one.  A point anchor (empty range) holds its whole line.
function M.thread_at(buf, row, col)
  local st = by_buf[buf]
  if not st then return nil end
  local best, best_size
  for _, thread in ipairs(st.threads) do
    local sr, sc, er, ec = M.anchor_range(buf, thread)
    if sr then
      local point = sr == er and sc == ec
      local after_start = row > sr or (row == sr and col >= sc)
      local before_end = row < er or (row == er and col < ec)
      if (point and row == sr) or (after_start and before_end) then
        local size = (er - sr) * 100000 + (ec - sc) + (thread.root.resolved and 1e12 or 0)
        if not best_size or size < best_size then best, best_size = thread, size end
      end
    end
  end
  return best
end

function M.find_comment(buf, id)
  local st = by_buf[buf]
  for _, thread in ipairs(st and st.threads or {}) do
    for _, comment in ipairs(thread.comments) do
      if comment.id == id then return thread, comment end
    end
  end
end

return M
