-- A float with the thread under the cursor.  It closes when the cursor leaves the line;
-- the same key again moves into it, where you can select text to reply about.

local render = require("lma.render")
local state = require("lma.state")

local M = {}

local ns = vim.api.nvim_create_namespace("lma_float")
local MAX_WIDTH = 80
local MAX_HEIGHT = 20

local float = { buf = nil, win = nil, source = nil, root = nil, rows = {} }

M.on_open = function(_) end

function M.is_open()
  return float.win ~= nil and vim.api.nvim_win_is_valid(float.win)
end

local function contents(thread)
  local out = render.new()
  render.thread(out, thread, 0, true)
  return out
end

function M.close()
  if M.is_open() then vim.api.nvim_win_close(float.win, true) end
end

function M.draw()
  if not M.is_open() then return end
  local thread = state.find_comment(float.source, float.root)
  if not thread then
    M.close()
    return
  end
  local out = contents(thread)
  render.write(float.buf, ns, out)
  float.rows = out.rows
end

function M.show(source)
  if M.is_open() then
    vim.api.nvim_set_current_win(float.win)
    return
  end
  local row, col = unpack(vim.api.nvim_win_get_cursor(0))
  local thread = state.thread_at(source, row - 1, col)
  if not thread then
    vim.notify("lma: no thread here", vim.log.levels.INFO)
    return
  end
  local out = contents(thread)
  local width = 20
  for _, line in ipairs(out.lines) do width = math.max(width, vim.fn.strdisplaywidth(line)) end
  float.buf = vim.api.nvim_create_buf(false, true)
  vim.bo[float.buf].bufhidden = "wipe"
  vim.bo[float.buf].filetype = "lmathread"
  float.source, float.root = source, thread.root.id
  float.win = vim.api.nvim_open_win(float.buf, false, {
    relative = "cursor", row = 1, col = 0,
    width = math.min(width + 1, MAX_WIDTH, vim.o.columns - 4),
    height = math.min(#out.lines, MAX_HEIGHT),
    border = "rounded", style = "minimal",
  })
  vim.wo[float.win].wrap, vim.wo[float.win].linebreak = true, true
  render.write(float.buf, ns, out)
  float.rows = out.rows
  vim.keymap.set("n", "q", M.close, { buffer = float.buf, desc = "lma: close the thread" })
  M.on_open(float.buf)

  local group = vim.api.nvim_create_augroup("lma_float", { clear = true })
  vim.api.nvim_create_autocmd({ "CursorMoved", "InsertEnter", "BufLeave" }, {
    group = group, buffer = source,
    callback = function(ev)
      -- moving into the float leaves the source buffer; that keeps it open
      if ev.event == "BufLeave" and vim.api.nvim_get_current_win() ~= float.win then
        vim.schedule(function()
          if vim.api.nvim_get_current_win() ~= float.win then M.close() end
        end)
        return true
      end
      if ev.event ~= "BufLeave" then
        local now = vim.api.nvim_win_get_cursor(0)[1]
        if now ~= row then
          M.close()
          return true
        end
      end
    end,
  })
  vim.api.nvim_create_autocmd("WinLeave", {
    group = group, buffer = float.buf,
    callback = function() vim.schedule(M.close) end,
  })
end

function M.context()
  return float.source, float.rows
end

function M.buf()
  return float.buf
end

return M
