-- A thread as lines of text, for the panel.  Each comment is a header (its author
-- and time) and its body below, indented by its depth in the thread:
--
--   Sam Lee · 11-19 19:40
--     why not `yield_results` here?
--     ↳ BraveFig (Author) · 11-19 19:41
--       on "yield_results"
--       `xf_mapping` fails fast, and...
--
-- `rows[row]` says what each line shows: { comment, body_start } for a body line, where
-- `body_start` is the character offset into the body at which the line starts (a reply's
-- `span` counts characters, which in Lua are UTF-32 units); { comment } for the others.

local M = {}

-- `at` is UTC; we show it in local time, month and day first.
local function when(at)
  local y, mo, d, h, mi, s = (at or ""):match("^(%d+)%-(%d+)%-(%d+)T(%d+):(%d+):(%d+)")
  if not y then return at or "" end
  local as_if_local = os.time({ year = y, month = mo, day = d, hour = h, min = mi, sec = s })
  local utc_offset = os.time() - os.time(os.date("!*t"))
  return os.date("%m-%d %H:%M", as_if_local + utc_offset)
end

local function chars(text)
  return vim.fn.strchars(text)
end

local function byte_of(text, char)
  local ok, byte = pcall(vim.str_byteindex, text, "utf-32", char, false)
  return ok and byte or #text
end

-- Appends one thread's lines to `out` = { lines, hls, rows }, each line indented by
-- `indent` spaces.  `with_resolved` false leaves resolved comments out.  `unread(comment)`,
-- when given, marks the comments it is true for with a dot before the author.
function M.thread(out, thread, indent, with_resolved, unread)
  local by_id = {}
  for _, comment in ipairs(thread.comments) do by_id[comment.id] = comment end
  -- each comment's body lines, so a reply's span can light up its parent's text
  local body_rows = {}

  local function add(text, row_info)
    out.lines[#out.lines + 1] = text
    out.rows[#out.lines] = row_info
    return #out.lines - 1
  end
  local function hl(row, s, e, group)
    out.hls[#out.hls + 1] = { row = row, col_start = s, col_end = e, group = group }
  end

  for _, comment in ipairs(thread.comments) do
    if with_resolved or not comment.resolved then
      local pad = (" "):rep(indent + 2 * comment.depth)
      local arrow = comment.depth > 0 and "↳ " or ""
      local dot = unread and unread(comment) and "● " or ""
      local stamp = " · " .. when(comment.at) .. (comment.resolved and " · resolved" or "")
      local header = pad .. arrow .. dot .. comment.author .. stamp
      local row = add(header, { comment = comment, thread = thread })
      if dot ~= "" then hl(row, #pad + #arrow, #pad + #arrow + #dot, "LmaUnread") end
      local author_start = #pad + #arrow + #dot
      hl(row, author_start, author_start + #comment.author, comment.resolved and "LmaResolved" or "LmaAuthor")
      hl(row, author_start + #comment.author, #header, "LmaTime")

      local body_pad = pad .. "  "
      local parent = comment.re and by_id[comment.re]
      if comment.span and parent then
        local quoted = vim.fn.strcharpart(parent.body, comment.span[1], comment.span[2] - comment.span[1])
        local text = body_pad .. 'on "' .. quoted:gsub("%s*\n%s*", " ") .. '"'
        hl(add(text, { comment = comment, thread = thread }), #body_pad, #text, "LmaQuote")
      end

      local start = 0
      body_rows[comment.id] = {}
      for _, body_line in ipairs(vim.split(comment.body, "\n", { plain = true })) do
        local text = body_line == "" and "" or body_pad .. body_line
        local r = add(text, { comment = comment, thread = thread, body_start = start, prefix = #body_pad })
        if comment.resolved then hl(r, 0, #text, "LmaResolved") end
        body_rows[comment.id][#body_rows[comment.id] + 1] = { row = r, start = start, text = body_line, prefix = #body_pad }
        start = start + chars(body_line) + 1
      end
    end
  end

  -- a reply about part of its parent lights that part up
  for _, comment in ipairs(thread.comments) do
    local parent_rows = comment.span and comment.re and body_rows[comment.re]
    if parent_rows and (with_resolved or not comment.resolved) then
      local s, e = comment.span[1], comment.span[2]
      for _, r in ipairs(parent_rows) do
        local line_end = r.start + chars(r.text)
        if s < line_end and e > r.start then
          local from = byte_of(r.text, math.max(s, r.start) - r.start)
          local to = byte_of(r.text, math.min(e, line_end) - r.start)
          hl(r.row, r.prefix + from, r.prefix + to, "LmaSpan")
        end
      end
    end
  end
end

function M.new()
  return { lines = {}, hls = {}, rows = {} }
end

-- Writes `out` into a scratch buffer and highlights it.
function M.write(buf, ns, out)
  vim.bo[buf].modifiable = true
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, out.lines)
  vim.bo[buf].modifiable = false
  vim.api.nvim_buf_clear_namespace(buf, ns, 0, -1)
  for _, h in ipairs(out.hls) do
    pcall(vim.api.nvim_buf_set_extmark, buf, ns, h.row, h.col_start, { end_col = h.col_end, hl_group = h.group })
  end
end

-- The comment a visual selection in a rendered buffer lies in, and the span of its body
-- the selection covers, or nil when the selection leaves the comment's body.
function M.span(rows, buffer_lines, sr, sc, er, ec)
  local first, last = rows[sr + 1], rows[er + 1]
  if not (first and last and first.body_start and last.body_start and first.comment == last.comment) then
    return nil
  end
  local function offset(info, text, col)
    local in_body = math.max(0, math.min(col - info.prefix, #text - info.prefix))
    return info.body_start + vim.str_utfindex(text:sub(info.prefix + 1), "utf-32", in_body, false)
  end
  local s = offset(first, buffer_lines[sr + 1], sc)
  local e = offset(last, buffer_lines[er + 1], ec)
  if e <= s then return nil end
  return first.comment, { s, e }
end

return M
