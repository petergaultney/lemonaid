-- The small window you write a comment in.  Writing it (:w, :x, ZZ) or <C-s> sends the
-- comment; q or closing the window keeps it as a draft (lma.drafts), which the next
-- comment on the same thing offers again.  Clearing the text and writing drops it.

local drafts = require("lma.drafts")

local M = {}

local HEIGHT = 8
local MAX_WIDTH = 80

local function first_line(body)
  return (body:match("^[^\n]*"))
end

-- `draft` must be claimed (lma.drafts.claim); the window releases it if it closes unsent.
local function open_window(draft, title, on_submit)
  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].buftype = "acwrite"
  vim.bo[buf].bufhidden = "wipe"
  vim.api.nvim_buf_set_name(buf, ("lma://comment-%d"):format(buf))
  vim.bo[buf].filetype = "markdown"
  if draft.body ~= "" then
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, vim.split(draft.body, "\n", { plain = true }))
  end
  local win = vim.api.nvim_open_win(buf, true, {
    relative = "cursor", row = 1, col = 0,
    width = math.min(MAX_WIDTH, vim.o.columns - 4), height = HEIGHT,
    border = "rounded", style = "minimal",
    title = (" %s · :w sends it, q keeps a draft "):format(title), title_pos = "center",
  })
  vim.wo[win].wrap, vim.wo[win].linebreak = true, true

  local function text()
    return (table.concat(vim.api.nvim_buf_get_lines(buf, 0, -1, false), "\n"):gsub("%s+$", ""))
  end

  local submitted = false
  local function keep()
    if submitted or not vim.api.nvim_buf_is_valid(buf) then return end
    draft.body = text()
    if draft.body ~= "" then drafts.save(draft) else drafts.remove(draft) end
  end

  -- Saved as you type, so nothing you wrote depends on this window staying open, and
  -- again as the window goes, for an edit made in the same step as the close, and when
  -- nvim exits with the window open.
  vim.api.nvim_create_autocmd({ "TextChanged", "TextChangedI", "TextChangedP", "InsertLeave", "BufUnload" }, {
    buffer = buf, callback = keep,
  })
  local on_exit = vim.api.nvim_create_autocmd("VimLeavePre", { callback = keep })

  local function submit()
    if submitted then return end
    submitted = true
    draft.body = text()
    vim.bo[buf].modified = false
    -- Closing later, not here: :x and ZZ quit the current window right after the
    -- write, and if we had closed ours that would be the document's.
    vim.schedule(function()
      if vim.api.nvim_win_is_valid(win) then vim.api.nvim_win_close(win, true) end
      if draft.body == "" then
        drafts.retire(draft)
        drafts.release(draft)
        return
      end
      drafts.save(draft)
      drafts.sent(draft)
      on_submit(draft)
    end)
  end

  vim.api.nvim_create_autocmd("BufWriteCmd", { buffer = buf, callback = submit })
  vim.api.nvim_create_autocmd("BufWipeout", {
    buffer = buf,
    callback = function()
      pcall(vim.api.nvim_del_autocmd, on_exit)
      if not submitted then drafts.release(draft) end
      if not submitted and draft.body ~= "" then
        vim.notify("lma: kept your draft; the comment key offers it again, :LmaDrafts lists them")
      end
    end,
  })
  vim.keymap.set({ "n", "i" }, "<C-s>", function()
    vim.cmd.stopinsert()
    submit()
  end, { buffer = buf, desc = "lma: send this comment" })
  vim.keymap.set("n", "q", function() vim.api.nvim_win_close(win, true) end,
    { buffer = buf, desc = "lma: close, keeping a draft" })
  if draft.body == "" then vim.cmd.startinsert() end
end

-- Opens the window for a comment of `kind` ("comment" or "reply") on `path`; a reply
-- names the comment it answers (`re`) and may carry a `span` and the `quote` it covers.  When drafts of the same
-- kind are waiting, asks which to continue first.  `on_submit(draft)` sends it; the
-- caller tells lma.drafts whether the server wrote it (`confirmed`) or not (`returned`).
function M.open(opts)
  local waiting = drafts.matching(opts.path, opts.kind, opts.re)
  if #waiting == 0 then
    local draft = drafts.new(opts.path, opts.kind, opts.re, opts.span, opts.quote)
    drafts.claim(draft)
    open_window(draft, opts.title, opts.on_submit)
    return
  end
  local choices = vim.list_extend({ "A new comment" }, waiting)
  vim.ui.select(choices, {
    prompt = "Drafts waiting here",
    format_item = function(item)
      return type(item) == "string" and item or ("Draft: " .. first_line(item.body))
    end,
  }, function(choice)
    if choice == nil then return end
    local draft, why
    if type(choice) == "table" then
      draft, why = drafts.claim_saved(choice)
      if not draft then
        vim.notify("lma: " .. why, vim.log.levels.WARN)
        return
      end
    else
      draft = drafts.new(opts.path, opts.kind, opts.re, opts.span, opts.quote)
      drafts.claim(draft)
    end
    -- A new selection replaces the draft's; without one it keeps its own, which is
    -- checked against its parent's text when it is sent.
    if opts.span then draft.span, draft.quote = opts.span, opts.quote end
    open_window(draft, opts.title, opts.on_submit)
  end)
end

return M
