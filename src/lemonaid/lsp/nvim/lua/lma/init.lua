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
-- about the selected part of it when there is a selection.  <leader>cx deletes a comment
-- and its replies, or a whole thread on its anchor; <leader>cm moves a thread to the
-- selected text; <leader>cw turns on saving the file after each comment, so the lemon
-- hears of it at once (off by default, so a batch of comments goes out on one :w).
--
-- A lemon's reply that arrives while you work is announced and marked unread until you
-- visit its thread; once nothing in the file is unread, its inbox row is marked read.

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
  keys = {
    comment = "<leader>cc", resolve = "<leader>cr", thread = "<leader>ct", panel = "<leader>cp",
    delete = "<leader>cx", move = "<leader>cm", autosave = "<leader>cw",
  },
  -- save the file once the server confirms a comment, reply, resolve or delete
  autosave = false,
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

local function announce(buf, arrived)
  if #arrived == 0 then return end
  local name = vim.fn.fnamemodify(path_of(buf), ":t")
  local first = arrived[1]
  local message = #arrived == 1
      and ("%s replied in %s: %s"):format(first.author, name, (first.body:match("^[^\n]*")))
    or ("%d new replies in %s"):format(#arrived, name)
  notify(message .. "  (" .. config.keys.panel .. " to see)")
end

function M.on_threads(_, params, ctx)
  local buf = vim.fn.bufnr(vim.uri_to_fname(params.uri))
  if buf == -1 or not vim.api.nvim_buf_is_loaded(buf) then return end
  -- threads for an older version of the buffer would place anchors from text that has
  -- moved since; keep what we have and ask for threads for the buffer as it is now
  local now = vim.lsp.util.buf_versions[buf]
  local stale = params.version ~= vim.NIL and params.version ~= nil and now and params.version ~= now
  if stale then
    state.on_stale(buf)
    return
  end
  local client = vim.lsp.get_client_by_id(ctx.client_id)
  local unread = params.unread ~= vim.NIL and params.unread or nil
  announce(buf, state.set(buf, params.threads, client and client.offset_encoding or "utf-16", unread))
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

-- Saving after a confirmed change, when turned on: the lemon's watcher reads the file.
local function save_if_auto(buf)
  if not config.autosave or not vim.api.nvim_buf_is_loaded(buf) or not vim.bo[buf].modified then return end
  local ok, err = pcall(vim.api.nvim_buf_call, buf, function() vim.cmd("silent write") end)
  if not ok then
    notify("couldn't save the file, so the lemon won't hear of it until you do: " .. tostring(err),
      vim.log.levels.WARN)
  end
end

-- You've looked at `thread`: its comments are read, and the inbox row drops them, marking
-- itself read once it lists none you haven't seen.
local function seen(buf, thread)
  local cleared = state.mark_seen(buf, thread)
  if #cleared > 0 then
    send.run(buf, "lemonaid.seen", function() return { uri = vim.uri_from_bufnr(buf), ids = cleared } end,
      function() end)
  end
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
          save_if_auto(buf)
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
        if err then
          kept(draft, err.message or vim.inspect(err))
        else
          drafts.confirmed(draft)
          save_if_auto(source)
        end
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
    if err then notify(err.message or vim.inspect(err), vim.log.levels.WARN) else save_if_auto(source) end
  end)
end

-- Deletes `comment` and every reply below it; a thread's first comment takes the thread.
local function delete(source, thread, comment)
  local below = 0
  local inside = false
  for _, c in ipairs(thread.comments) do
    if c == comment then
      inside = true
    elseif inside and c.depth > comment.depth then
      below = below + 1
    elseif inside then
      break
    end
  end
  local what = comment == thread.root and "this thread" or ("%s's comment"):format(comment.author)
  local question = below > 0 and ("Delete %s and %d %s below it?"):format(what, below, below == 1 and "reply" or "replies")
    or ("Delete %s?"):format(what)
  if vim.fn.confirm(question, "&Delete\n&Keep", 2) ~= 1 then return end
  send.run(source, "lemonaid.delete", function()
    return { uri = vim.uri_from_bufnr(source), id = comment.id }
  end, function(err)
    if err then notify(err.message or vim.inspect(err), vim.log.levels.WARN) else save_if_auto(source) end
  end)
end

-- Moves a thread's anchor to the selected text.  The markers are hidden, so this is the
-- way to re-anchor one; with several threads in the file, you choose which.
local function move(buf)
  local mode = vim.fn.mode()
  if mode ~= "v" and mode ~= "V" then
    notify("select the text to move a thread to, then " .. config.keys.move, vim.log.levels.WARN)
    return
  end
  local sr, sc, er, ec = selection.take(buf)
  if not sr then return end
  local selected = vim.api.nvim_buf_get_text(buf, sr, sc, er, ec, {})
  local st = state.get(buf)
  -- a thread whose anchor is gone can be moved too, which is how to repair it
  local threads = st and st.threads or {}
  if #threads == 0 then
    notify("no thread in this file to move")
    return
  end
  local function moved(thread)
    if not thread then return end
    send.run(buf, "lemonaid.reanchor", function()
      -- the buffer may have changed or reloaded since you selected, as before a resend
      local ok, now = pcall(vim.api.nvim_buf_get_text, buf, sr, sc, er, ec, {})
      if not (ok and vim.deep_equal(now, selected)) then
        notify("the text you selected has changed; select it again", vim.log.levels.WARN)
        return nil
      end
      local encoding = send.client(buf).offset_encoding
      return {
        uri = vim.uri_from_bufnr(buf), id = thread.root.id,
        range = { start = state.to_lsp(buf, sr, sc, encoding), ["end"] = state.to_lsp(buf, er, ec, encoding) },
      }
    end, function(err)
      if err then notify(err.message or vim.inspect(err), vim.log.levels.WARN) else save_if_auto(buf) end
    end)
  end
  if #threads == 1 then return moved(threads[1]) end
  vim.ui.select(threads, {
    prompt = "Move which thread here?",
    format_item = function(t) return ("%s: %s"):format(t.root.author, (t.root.body:match("^[^\n]*"))) end,
  }, moved)
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
    vim.keymap.set("n", config.keys.delete, function()
      local source, rows = context()
      local info = rows[vim.api.nvim_win_get_cursor(0)[1]]
      if info then delete(source, info.thread, info.comment or info.thread.root) end
    end, { buffer = rendered_buf, desc = "lma: delete this comment and its replies" })
  end
end

-- Markers moved by hand, or threads for an older version: the server sends the threads
-- again, from the buffer as it is now.  At most once per version of the buffer, so a
-- marker that can never match (whatever the reason) doesn't ask forever.
local asked_at = {}
state.on_stale = function(buf)
  local version = vim.lsp.util.buf_versions[buf]
  if version ~= nil and asked_at[buf] == version then return end
  asked_at[buf] = version
  send.run(buf, "lemonaid.refresh", function() return { uri = vim.uri_from_bufnr(buf) } end, function() end)
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
    -- our own earlier mapping, when we map again after a reload, is not theirs to yield to
    local ours = (existing.desc or ""):sub(1, 4) == "lma:"
    if existing.buffer == 1 and not ours then before[mode] = existing end
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

local function map_shared_keys(buf)
  map(buf, config.keys.comment, { "n", "x" }, comment_on_code, "lma: comment on this line or selection")
  map(buf, config.keys.panel, { "n" }, panel.toggle, "lma: toggle the thread panel")
end

function M.on_attach(_, buf)
  map_shared_keys(buf)
  local function here()
    local cursor = vim.api.nvim_win_get_cursor(0)
    return state.thread_at(buf, cursor[1] - 1, cursor[2])
  end
  vim.keymap.set("n", config.keys.thread, function()
    float.show(buf)
    seen(buf, here())
  end, { buffer = buf, desc = "lma: show the thread here; again to move into it" })
  vim.keymap.set("n", config.keys.delete, function()
    local thread = here()
    if thread then delete(buf, thread, thread.root) else notify("no thread here") end
  end, { buffer = buf, desc = "lma: delete the thread here" })
  vim.keymap.set("x", config.keys.move, function() move(buf) end,
    { buffer = buf, desc = "lma: move a thread to the selected text" })
  vim.keymap.set("n", config.keys.move, function() move(buf) end,
    { buffer = buf, desc = "lma: move a thread to the selected text" })
  vim.keymap.set("n", config.keys.resolve, function()
    local thread = state.thread_at(buf, vim.api.nvim_win_get_cursor(0)[1] - 1, vim.api.nvim_win_get_cursor(0)[2])
    if thread then resolve(buf, thread.root) else notify("no thread here") end
  end, { buffer = buf, desc = "lma: resolve the thread here" })

  watch(buf)
  local group = vim.api.nvim_create_augroup("lma_buf_" .. buf, { clear = true })
  vim.api.nvim_create_autocmd("BufEnter", { group = group, buffer = buf, callback = function() panel.follow(buf) end })
  -- visiting a thread with an unread reply reads it
  vim.api.nvim_create_autocmd("CursorMoved", {
    group = group, buffer = buf,
    callback = function() if state.has_unread(buf) then seen(buf, here()) end end,
  })
  -- A reload (:edit, :checktime after a lemon writes the file) sets the filetype again, and
  -- its ftplugin maps its own keys over ours; the client stays attached, so map ours again.
  vim.api.nvim_create_autocmd("FileType", { group = group, buffer = buf, callback = function() map_shared_keys(buf) end })
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

-- Starts `lemonaid lsp` without waiting for a Python or Markdown buffer, so a lemon's
-- `lemonaid editor open` reaches this nvim from the start.  Call it after enabling the
-- server; a buffer that opens later attaches to it, or to a server for its own workspace.
function M.start_server()
  if #vim.lsp.get_clients({ name = "lemonaid" }) > 0 then return end
  local server = vim.lsp.config["lemonaid"]
  if not server then return end
  vim.lsp.start(vim.tbl_extend("force", server, { root_dir = vim.fn.getcwd() }), { attach = false })
end

function M.setup(opts)
  opts = opts or {}
  config.keys = vim.tbl_extend("force", config.keys, opts.keys or {})
  config.yield_to = opts.yield_to or config.yield_to
  if opts.autosave ~= nil then config.autosave = opts.autosave end
  vim.keymap.set("n", config.keys.autosave, function()
    config.autosave = not config.autosave
    notify("saving after each comment is " .. (config.autosave and "on" or "off"))
  end, { desc = "lma: save the file after each comment, or stop" })
  vim.api.nvim_create_user_command("LmaDrafts", list_drafts,
    { desc = "List the comments you wrote that the server never confirmed" })
  vim.api.nvim_create_user_command("LmaMarkers", function()
    state.show_markers = not state.show_markers
    for _, buf in ipairs(vim.api.nvim_list_bufs()) do state.refresh_conceal(buf) end
  end, { desc = "Show or hide the comment markers" })
end

return M
