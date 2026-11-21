-- Each buffer's threads, as the server last sent them in `lemonaid/threads`, and the
-- marks that draw them.  The server sends threads only when the comments change, not
-- when text moves, so we place an extmark at each anchor when they arrive and let nvim
-- carry it as you edit.
--
-- A thread is { anchor = LSP range or nil, comments = { ... }, root, mark }: `comments`
-- in tree order, each with its `depth` and `by` ("lemon" or "person"); `root` the first;
-- `mark` the anchor's extmark id.
--
-- A lemon's comment that arrives after the buffer's first notification is unread until
-- you visit its thread: its anchor gets a different sign, and `unread` lists its id.

local M = {}

M.ns = vim.api.nvim_create_namespace("lma")
local conceal_ns = vim.api.nvim_create_namespace("lma_conceal")
-- a plain mark on each of the threads' own markers, to tell where they are now
local marker_ns = vim.api.nvim_create_namespace("lma_markers")

local HINT_LENGTH = 60

-- by_buf[buf] = { threads, encoding, unread = { [id] = true }, ... }
local by_buf = {}

-- Called with the buffer when one of its hidden markers no longer holds the marker's text
-- where the last notification put it, as after moving markers by hand; set by init.
M.on_stale = function(_) end

-- Show the markers as written, for editing near them.
M.show_markers = false

-- Defaults only: a colorscheme that sets these groups wins.  Run again on ColorScheme,
-- because :hi clear drops them.
local function define_default_highlights()
  local set = function(name, link) vim.api.nvim_set_hl(0, name, { link = link, default = true }) end
  set("LmaAnchor", "LspReferenceText") -- the text a thread is about
  set("LmaSign", "DiagnosticHint")
  set("LmaUnread", "DiagnosticWarn") -- the sign of a thread with a reply you haven't seen
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

local function is_unread(st, thread)
  for _, comment in ipairs(thread.comments) do
    if st.unread[comment.id] then return true end
  end
  return false
end

-- Whether `text` after line `row` would run past the edge of a window showing the buffer
-- with 'wrap' on, where text at the end of the line is cut off.
local function would_wrap(buf, row, text)
  local line_width = vim.fn.strdisplaywidth(line(buf, row) or "")
  for _, win in ipairs(vim.fn.win_findbuf(buf)) do
    local width = vim.api.nvim_win_get_width(win) - vim.fn.getwininfo(win)[1].textoff
    if vim.wo[win].wrap and line_width + vim.fn.strdisplaywidth(text) > width then return true end
  end
  return false
end

-- `at`, when given, is where the anchor is now (a redraw); else the notification's range.
local function draw_anchor(buf, thread, st, at)
  local sr, sc, er, ec
  if at then
    sr, sc, er, ec = unpack(at)
  else
    sr, sc = M.to_byte(buf, thread.anchor.start, st.encoding)
    er, ec = M.to_byte(buf, thread.anchor["end"], st.encoding)
  end
  local resolved = thread.root.resolved
  local unread = is_unread(st, thread)
  local replies = #thread.comments - 1
  local hint = ("%s: %s%s"):format(thread.root.author, first_line(thread.root.body),
    replies > 0 and (" (+%d)"):format(replies) or "")
  -- the line the anchor's text ends on: a whole-line anchor ends at the start of the next
  local last_row = (ec == 0 and er > sr) and er - 1 or er
  local below = not resolved and would_wrap(buf, last_row, "  " .. hint)
  local mark = {
    end_row = er, end_col = ec,
    hl_group = not resolved and "LmaAnchor" or nil,
    sign_text = resolved and "✓" or unread and "●" or "┃",
    sign_hl_group = resolved and "LmaResolved" or unread and "LmaUnread" or "LmaSign",
    virt_text = not resolved and not below and { { "  " .. hint, "LmaHint" } } or nil,
    virt_text_pos = "eol",
    right_gravity = false, end_right_gravity = true,
    priority = 4500,
  }
  local ok, id = pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, sr, sc, mark)
  thread.mark = ok and id or nil
  -- on a line that wraps, the end of the line has no room: the hint gets a line of its own
  if below then
    pcall(vim.api.nvim_buf_set_extmark, buf, M.ns, last_row, 0, {
      virt_lines = { { { "  ┃ " .. hint, "LmaHint" } } },
      priority = 4500,
    })
  end
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
  local off = {} -- markers no longer where the notification put them
  for _, marker in ipairs(st.markers or {}) do
    local at = vim.api.nvim_buf_get_extmark_by_id(buf, marker_ns, marker.id, { details = true })
    if at[1] then
      local sr, sc, er, ec = at[1], at[2], at[3].end_row, at[3].end_col
      local ok, text = pcall(vim.api.nvim_buf_get_text, buf, sr, sc, er, ec, {})
      -- a whole-line marker must still be a whole line: text typed at its start sits
      -- inside the line, and hiding the line would hide that text
      local still_whole = not marker.whole_line or (sc == 0 and ec == 0 and er == sr + 1)
      if ok and still_whole and table.concat(text, "\n") == marker.text then
        if not M.show_markers then
          local mark = marker.whole_line and { end_row = er - 1, conceal_lines = "" }
            or { end_row = er, end_col = ec, conceal = "" }
          pcall(vim.api.nvim_buf_set_extmark, buf, conceal_ns, sr, sc, mark)
        end
      else
        off[marker.id] = true
      end
    else
      off[marker.id] = true
    end
  end
  -- a marker newly out of place: ask the server again, once for it; its answer is a new
  -- notification, which starts afresh
  st.asked_for = st.asked_for or {}
  local newly = false
  for id in pairs(off) do
    if not st.asked_for[id] then newly, st.asked_for[id] = true, true end
  end
  if newly then M.on_stale(buf) end
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

-- `unread_ids` are the comments the file's inbox row says you haven't seen, so a reply
-- written while the file was closed is marked when it opens.  Returns the comments newly
-- unread, for announcing.
function M.set(buf, threads, encoding, unread_ids)
  for _, thread in ipairs(threads) do
    thread.anchor = value(thread.anchor)
    for _, comment in ipairs(thread.comments) do
      comment.re, comment.span = value(comment.re), value(comment.span)
    end
    thread.root = thread.comments[1]
  end
  -- the server sorts anchored threads by position and puts orphans last
  local previous = by_buf[buf]
  local st = {
    threads = threads, encoding = encoding, following = previous and previous.following, tick = 0,
    unread = {},
    read = previous and previous.read or {}, -- ids you have visited, never marked again
  }
  -- a lemon's comment new since the last notification is unread, and so is one the inbox
  -- row lists; on the buffer's first notification nothing else is, since all would be new
  local from_inbox = {}
  for _, id in ipairs(unread_ids or {}) do from_inbox[id] = true end
  local known = {}
  for _, thread in ipairs(previous and previous.threads or {}) do
    for _, comment in ipairs(thread.comments) do known[comment.id] = true end
  end
  local arrived = {}
  for _, thread in ipairs(threads) do
    for _, comment in ipairs(thread.comments) do
      local id = comment.id
      local new_reply = previous and not known[id] and comment.by == "lemon" and not comment.resolved
      if previous and previous.unread[id] then
        st.unread[id] = true
      elseif not st.read[id] and (new_reply or (from_inbox[id] and not known[id])) then
        st.unread[id] = true
        arrived[#arrived + 1] = comment
      end
    end
  end
  by_buf[buf] = st
  vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
  for _, thread in ipairs(threads) do
    if thread.anchor then draw_anchor(buf, thread, st) end
  end
  place_markers(buf, st)
  follow_edits(buf, st)
  M.refresh_conceal(buf)
  M.allow_conceal(buf)
  -- a marker already out of place when the threads arrive (they describe an older version
  -- of the buffer) can't be followed; ask for threads that match the buffer now
  local expected = 0
  for _, thread in ipairs(threads) do expected = expected + #(thread.markers or {}) end
  if #st.markers < expected then M.on_stale(buf) end
  return arrived
end

-- Draws the anchors again where nvim has carried them since the notification.
function M.redraw(buf)
  local st = by_buf[buf]
  if not st then return end
  local now = {}
  for i, thread in ipairs(st.threads) do
    local sr, sc, er, ec = M.anchor_range(buf, thread)
    if sr then now[i] = { sr, sc, er, ec } end
  end
  vim.api.nvim_buf_clear_namespace(buf, M.ns, 0, -1)
  for i, thread in ipairs(st.threads) do
    if now[i] then draw_anchor(buf, thread, st, now[i]) else thread.mark = nil end
  end
end

-- You have seen `thread`: its comments are read.  Returns the ids that were unread.
function M.mark_seen(buf, thread)
  local st = by_buf[buf]
  if not (st and thread) then return {} end
  local cleared = {}
  for _, comment in ipairs(thread.comments) do
    st.read[comment.id] = true
    if st.unread[comment.id] then
      st.unread[comment.id] = nil
      cleared[#cleared + 1] = comment.id
    end
  end
  if #cleared > 0 then M.redraw(buf) end
  return cleared
end

function M.has_unread(buf)
  local st = by_buf[buf]
  return st ~= nil and next(st.unread) ~= nil
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
