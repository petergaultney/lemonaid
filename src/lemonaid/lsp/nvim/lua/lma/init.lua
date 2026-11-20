-- Review comments kept in the file they are about, drawn from what lemonaid's server
-- (`lemonaid lsp`, configured in lsp/lemonaid.lua) sends, and written through its
-- commands.  The server owns the format: we never write a marker or a record ourselves.
--
--   vim.opt.rtp:append(<`lemonaid editor nvim-path`>)
--   require("lma").setup({ keys = { ... }, yield_to = function(buf) ... end })
--   vim.lsp.enable("lemonaid")
--
--   state     each buffer's threads, anchor marks and concealed markers
--   render    a thread as lines, for the panel and the float
--   panel     every thread beside the buffer
--   float     the thread under the cursor
--   compose   the window you write a comment in
--   drafts    what you wrote, until the server confirms it
--   send      the server's commands, reloading once when a lemon wrote the file
--
-- One key, <leader>cc by default, comments: on code it anchors a new thread on the line
-- or the selection; in the panel or a float it replies to the comment under the cursor,
-- about the selected part of it when there is a selection.

local compose = require("lma.compose")
local drafts = require("lma.drafts")
local float = require("lma.float")
local panel = require("lma.panel")
local render = require("lma.render")
local selection = require("lma.selection")
local send = require("lma.send")
local state = require("lma.state")

local M = {}

local config = {
  keys = { comment = "<leader>cc", resolve = "<leader>cr", thread = "<leader>ct", panel = "<leader>cp" },
  -- yield_to(buf): true to leave the comment and panel keys to the buffer's own mappings
  -- in a buffer with no threads (a vault doc whose comments are CriticMarkup)
  yield_to = function(_) return false end,
}

local function notify(message, level)
  vim.notify("lma: " .. message, level or vim.log.levels.INFO)
end

local function path_of(buf)
  return vim.api.nvim_buf_get_name(buf)
end

-- ── What the server sends ────────────────────────────────────────────

local function redraw_views(buf)
  if panel.source() == buf then panel.draw() end
  float.draw()
end

function M.on_threads(_, params, ctx)
  local buf = vim.fn.bufnr(vim.uri_to_fname(params.uri))
  if buf == -1 or not vim.api.nvim_buf_is_loaded(buf) then return end
  local client = vim.lsp.get_client_by_id(ctx.client_id)
  state.set(buf, params.threads, client and client.offset_encoding or "utf-16")
  panel.follow(buf)
  redraw_views(buf)
end

local function usable_window()
  local win = vim.api.nvim_get_current_win()
  if vim.api.nvim_win_get_config(win).relative == "" then return win end
  for _, each in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
    if vim.api.nvim_win_get_config(each).relative == "" then return each end
  end
end

-- `lemonaid editor open`: show the file in a split of this tab, or in the window that
-- already shows it, and leave the cursor where it was unless asked to take it.
function M.show_document(err, params, ctx)
  if params.external then return vim.lsp.handlers["window/showDocument"](err, params, ctx) end
  local fname = vim.uri_to_fname(params.uri)
  local before = vim.api.nvim_get_current_win()
  local buf = vim.fn.bufadd(fname)
  vim.fn.bufload(buf)
  vim.bo[buf].buflisted = true
  local win = vim.fn.win_findbuf(buf)[1]
  if not (win and vim.api.nvim_win_get_tabpage(win) == vim.api.nvim_get_current_tabpage()) then
    vim.api.nvim_set_current_win(usable_window() or before)
    vim.cmd("vertical sbuffer " .. buf)
    win = vim.api.nvim_get_current_win()
  end
  if win == before and not params.takeFocus then
    -- you are in that window: moving its cursor would be taking the cursor, so we say
    -- where instead
    if params.selection then
      notify(("%s, line %d"):format(vim.fn.fnamemodify(fname, ":~:."), params.selection.start.line + 1))
    end
    return { success = true }
  end
  if params.selection then
    local client = vim.lsp.get_client_by_id(ctx.client_id)
    local row, col = state.to_byte(buf, params.selection.start, client and client.offset_encoding or "utf-16")
    vim.api.nvim_win_set_cursor(win, { row + 1, col })
    vim.api.nvim_win_call(win, function() vim.cmd("normal! zz") end)
  end
  vim.api.nvim_set_current_win(params.takeFocus and win or before)
  return { success = true }
end

-- ── Commenting ───────────────────────────────────────────────────────

-- The selection, or the cursor's line, as 0-based (row, byte col) start and exclusive end.
local function chosen_text(buf)
  local mode = vim.fn.mode()
  if mode == "\22" then
    notify("a block selection can't be commented; use v or V", vim.log.levels.WARN)
    return nil
  end
  if mode ~= "v" and mode ~= "V" then
    local row = vim.api.nvim_win_get_cursor(0)[1] - 1
    return row, 0, row, #vim.api.nvim_get_current_line()
  end
  return selection.take(buf)
end

local function kept(draft, message)
  drafts.returned(draft)
  notify(message .. " Your draft is kept; " .. config.keys.comment .. " offers it again.", vim.log.levels.WARN)
end

local function comment_on_code(buf)
  local sr, sc, er, ec = chosen_text(buf)
  if not sr then return end
  local selected = vim.api.nvim_buf_get_text(buf, sr, sc, er, ec, {})
  local function still_selected()
    local ok, now = pcall(vim.api.nvim_buf_get_text, buf, sr, sc, er, ec, {})
    return ok and vim.deep_equal(now, selected)
  end
  compose.open({
    path = path_of(buf), kind = "comment", title = "Comment",
    on_submit = function(draft)
      send.run(buf, "lemonaid.comment", function()
        -- you may have typed, or nvim reloaded the file, since you chose the text
        if not still_selected() then
          kept(draft, "The text you selected has changed; select it again.")
          return nil
        end
        local encoding = send.client(buf).offset_encoding
        return {
          uri = vim.uri_from_bufnr(buf),
          range = { start = state.to_lsp(buf, sr, sc, encoding), ["end"] = state.to_lsp(buf, er, ec, encoding) },
          body = draft.body,
        }
      end, function(err)
        if not err then
          drafts.confirmed(draft)
        elseif send.reason(err) == "moved" then
          kept(draft, "The buffer changed while the comment was written; select the text again.")
        else
          kept(draft, err.message or vim.inspect(err))
        end
      end)
    end,
  })
end

local function reply(source, rows, rendered_buf)
  local comment, span
  if selection.is_visual() then
    local sr, sc, er, ec = selection.take(rendered_buf)
    if not sr then return end
    local lines = vim.api.nvim_buf_get_lines(rendered_buf, 0, -1, false)
    comment, span = render.span(rows, lines, sr, sc, er, ec)
    if not comment then
      notify("select text inside one comment to reply about it", vim.log.levels.WARN)
      return
    end
  else
    local info = rows[vim.api.nvim_win_get_cursor(0)[1]]
    comment = info and (info.comment or info.thread.root)
    if not comment then return end
  end
  compose.open({
    path = path_of(source), kind = "reply", re = comment.id, title = "Reply to " .. comment.author,
    -- the text the span covers, so we can tell at sending that it still says that
    span = span, quote = span and vim.fn.strcharpart(comment.body, span[1], span[2] - span[1]),
    on_submit = function(draft)
      send.run(source, "lemonaid.reply", function()
        if draft.span then
          local _, parent = state.find_comment(source, draft.re)
          local now = parent and vim.fn.strcharpart(parent.body, draft.span[1], draft.span[2] - draft.span[1])
          if now ~= draft.quote then
            kept(draft, "The comment you replied about no longer says what you selected; select it again.")
            return nil
          end
        end
        -- the server checks the quote too, against the text it edits, which can be newer
        -- than the threads we were last sent
        return {
          uri = vim.uri_from_bufnr(source), re = draft.re, body = draft.body,
          span = draft.span, quote = draft.span and draft.quote,
        }
      end, function(err)
        if err then kept(draft, err.message or vim.inspect(err)) else drafts.confirmed(draft) end
      end)
    end,
  })
end

local function resolve(source, comment)
  if comment.resolved then
    notify("that comment is resolved already")
    return
  end
  send.run(source, "lemonaid.resolve", function()
    return { uri = vim.uri_from_bufnr(source), id = comment.id }
  end, function(err)
    if err then notify(err.message or vim.inspect(err), vim.log.levels.WARN) end
  end)
end

-- Keys for a buffer that shows threads (the panel, a float): reply and resolve.
local function rendered_keys(context)
  return function(rendered_buf)
    vim.keymap.set({ "n", "x" }, config.keys.comment, function()
      local source, rows = context()
      reply(source, rows, rendered_buf)
    end, { buffer = rendered_buf, desc = "lma: reply to this comment" })
    vim.keymap.set("n", config.keys.resolve, function()
      local source, rows = context()
      local info = rows[vim.api.nvim_win_get_cursor(0)[1]]
      if info then resolve(source, info.comment or info.thread.root) end
    end, { buffer = rendered_buf, desc = "lma: resolve this comment and its replies" })
  end
end

panel.on_open = rendered_keys(panel.context)
float.on_open = rendered_keys(float.context)

-- ── Buffers the server attaches to ───────────────────────────────────

-- A lemon writes a file whose buffer has no unsaved changes, and nvim reloads it; nvim
-- itself only looks on focus and after shell commands, so we watch.  We watch the file's
-- directory, not the file: a write that replaces the file, or removes it and makes it
-- again, ends a watch on the file itself.
local watchers = {}

local function unwatch(buf)
  local handle = watchers[buf]
  watchers[buf] = nil
  if handle and not handle:is_closing() then
    handle:stop()
    handle:close()
  end
end

local function watch(buf)
  unwatch(buf)
  local path = path_of(buf)
  if path == "" then return end
  local name = vim.fs.basename(path)
  local handle = vim.uv.new_fs_event()
  if not handle then return end
  local ok = handle:start(vim.fs.dirname(path), {}, vim.schedule_wrap(function(err, changed)
    if err or watchers[buf] ~= handle or not vim.api.nvim_buf_is_loaded(buf) then return end
    -- some systems name no file; then any change in the directory is worth a look
    if changed and vim.fs.basename(changed) ~= name then return end
    if not vim.bo[buf].modified then vim.cmd("checktime " .. buf) end
  end))
  if ok then
    watchers[buf] = handle
  else
    handle:close()
  end
end

local function map(buf, lhs, modes, action, desc)
  local before = {}
  for _, mode in ipairs(modes) do
    local existing = vim.fn.maparg(lhs, mode, false, true)
    if existing.buffer == 1 then before[mode] = existing end
  end
  vim.keymap.set(modes, lhs, function()
    local mode = vim.fn.mode():sub(1, 1):lower() == "n" and "n" or "x"
    local theirs = before[mode]
    if theirs and not (state.get(buf) and #state.get(buf).threads > 0) and config.yield_to(buf) then
      if theirs.callback then return theirs.callback() end
      return vim.api.nvim_feedkeys(vim.keycode(theirs.rhs), "m", false)
    end
    action(buf)
  end, { buffer = buf, desc = desc })
end

function M.on_attach(_, buf)
  map(buf, config.keys.comment, { "n", "x" }, comment_on_code, "lma: comment on this line or selection")
  map(buf, config.keys.panel, { "n" }, panel.toggle, "lma: toggle the thread panel")
  vim.keymap.set("n", config.keys.thread, function() float.show(buf) end,
    { buffer = buf, desc = "lma: show the thread here; again to move into it" })
  vim.keymap.set("n", config.keys.resolve, function()
    local thread = state.thread_at(buf, vim.api.nvim_win_get_cursor(0)[1] - 1, vim.api.nvim_win_get_cursor(0)[2])
    if thread then resolve(buf, thread.root) else notify("no thread here") end
  end, { buffer = buf, desc = "lma: resolve the thread here" })

  watch(buf)
  local group = vim.api.nvim_create_augroup("lma_buf_" .. buf, { clear = true })
  vim.api.nvim_create_autocmd("BufEnter", { group = group, buffer = buf, callback = function() panel.follow(buf) end })
  vim.api.nvim_create_autocmd("BufWinEnter", { group = group, buffer = buf, callback = function() state.allow_conceal(buf) end })
  -- :saveas and :file change the name we watch for
  vim.api.nvim_create_autocmd("BufFilePost", { group = group, buffer = buf, callback = function() watch(buf) end })
  vim.api.nvim_create_autocmd({ "BufUnload", "BufWipeout" }, {
    group = group, buffer = buf,
    callback = function()
      unwatch(buf)
      state.forget(buf)
      vim.api.nvim_del_augroup_by_id(group)
    end,
  })
end

-- ── Setup ────────────────────────────────────────────────────────────

local function list_drafts()
  local items = vim.tbl_map(function(draft)
    local what = draft.kind == "reply" and ("reply to " .. draft.re) or "comment"
    return { filename = draft.path, lnum = 1, text = what .. ": " .. (draft.body:match("^[^\n]*")) }
  end, drafts.all())
  if #items == 0 then
    notify("no drafts")
    return
  end
  vim.fn.setqflist({}, " ", { title = "lma drafts", items = items })
  vim.cmd.copen()
end

function M.setup(opts)
  opts = opts or {}
  config.keys = vim.tbl_extend("force", config.keys, opts.keys or {})
  config.yield_to = opts.yield_to or config.yield_to
  vim.api.nvim_create_user_command("LmaDrafts", list_drafts,
    { desc = "List the comments you wrote that the server never confirmed" })
  vim.api.nvim_create_user_command("LmaMarkers", function()
    state.show_markers = not state.show_markers
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do state.refresh_conceal(buf) end
  end, { desc = "Show or hide the comment markers" })
end

return M
