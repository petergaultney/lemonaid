-- lemonaid's review-comments server (`lemonaid lsp`, lemonaid's docs/comments.md), which
-- reads and writes the comments a file keeps about itself.  lua/lma draws what it sends
-- and calls its commands.  With this directory on 'runtimepath' (`lemonaid editor
-- nvim-path` prints it), `vim.lsp.enable("lemonaid")` starts it.
local lma = require("lma")

return {
  cmd = { "lemonaid", "lsp" },
  filetypes = { "python", "markdown" },
  root_markers = { ".git" },
  handlers = {
    ["lemonaid/threads"] = lma.on_threads,
    -- nvim's own handler loads a file it isn't asked to focus without showing it
    ["window/showDocument"] = lma.show_document,
  },
  on_attach = lma.on_attach,
}
