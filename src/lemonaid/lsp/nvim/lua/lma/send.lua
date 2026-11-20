-- Running the server's commands (`lemonaid.comment`, `.reply`, `.resolve`).
--
-- After a lemon writes a file, the server refuses an edit to the buffer until nvim has
-- reloaded it (`data.reason` "diverged"), since the edit would be lost on save.  When
-- the buffer has no changes of its own we reload it and send once more.  We retry only
-- after that outright refusal, never on silence: a command the server may still carry
-- out must not be sent twice.

local M = {}

local function client_for(buf)
  return vim.lsp.get_clients({ bufnr = buf, name = "lemonaid" })[1]
end

function M.client(buf)
  return client_for(buf)
end

local function reason(err)
  return type(err) == "table" and type(err.data) == "table" and err.data.reason or nil
end

-- `checktime` reloads an unmodified buffer whose file changed ('autoread').  nvim tells
-- the server with didClose and didOpen, which it sends before any later request, so the
-- server has the reloaded text by the time our command arrives.
local function reload(buf)
  vim.api.nvim_buf_call(buf, function() vim.cmd("checktime") end)
end

-- Runs `command` on `buf` with the argument `argument()` returns, computed again for
-- the retry, and calls `done(err, result)`.  `argument()` returns nil to give up, having
-- said why.
function M.run(buf, command, argument, done)
  local client = client_for(buf)
  if not client then
    done({ message = "lemonaid lsp isn't attached to this buffer" })
    return
  end
  local function attempt(retried)
    local arg = argument()
    if arg == nil then return end
    client:exec_cmd({ title = command, command = command, arguments = { arg } }, { bufnr = buf },
      function(err, result)
        -- the server marks "diverged" only before it sent any edit, so a resend can't
        -- write the comment twice
        local still_here = vim.api.nvim_buf_is_loaded(buf) and not client:is_stopped()
        if reason(err) == "diverged" and not retried and still_here and not vim.bo[buf].modified then
          reload(buf)
          attempt(true)
          return
        end
        done(err, result)
      end)
  end
  attempt(false)
end

M.reason = reason

return M
