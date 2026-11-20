-- lemonaid's nvim client (src/lemonaid/lsp/nvim) driven in headless nvim against a real
-- `lemonaid lsp`.  test_nvim_client.py runs it with PLUGIN (the client's directory) and
-- WORK (a scratch directory holding a .git, so the server's workspace is WORK), and
-- `lemonaid` on PATH; it writes one line per check to WORK/results.txt.
local plugin, work = vim.env.PLUGIN, vim.env.WORK
vim.opt.rtp:prepend(plugin)
vim.g.mapleader = " "
vim.cmd("filetype plugin on")
vim.o.swapfile = false
local results, failed = {}, 0
local function check(name, ok, detail)
  results[#results + 1] = (ok and "PASS " or "FAIL ") .. name .. (ok and "" or ("  " .. vim.inspect(detail)))
  if not ok then failed = failed + 1 end
  -- as we go, so a run that hangs still says how far it got
  vim.fn.writefile({ results[#results] }, vim.env.WORK .. "/progress.txt", "a")
end
local function wait(ms, cond) return vim.wait(ms, cond, 20) end
local function text(buf) return table.concat(vim.api.nvim_buf_get_lines(buf or 0, 0, -1, false), "\n") end
local function lemonaid(...)
  return vim.system({ "lemonaid", ... }, { text = true }):wait()
end
local notes = {}
local real_notify = vim.notify
vim.notify = function(msg, level) notes[#notes + 1] = msg end

local function run()
-- A buffer marked `other_comments` keeps its own comment key, as a vault doc keeps
-- another comment plugin's (in Caleb's config, critic.lua's).
vim.api.nvim_create_autocmd("FileType", {
  pattern = "markdown",
  callback = function(ev)
    if vim.b[ev.buf].other_comments then
      vim.keymap.set("n", "<leader>cc", function() vim.b[ev.buf].other_key_pressed = true end, { buffer = ev.buf })
    end
  end,
})
require("lma").setup({ yield_to = function(buf) return vim.b[buf].other_comments == true end })
vim.lsp.enable("lemonaid")

local errors = {}
local function watch_errors(buf)
  local client = vim.lsp.get_clients({ bufnr = buf, name = "lemonaid" })[1]
  if client.__wrapped then return end
  client.__wrapped = true
  local exec = client.exec_cmd
  client.exec_cmd = function(self, cmd, ctx, handler)
    return exec(self, cmd, ctx, function(err, res, ...)
      if err then errors[#errors + 1] = { cmd.command, err.data and err.data.reason, err.message } end
      return handler(err, res, ...)
    end)
  end
end

local code = work .. "/code.py"
vim.fn.writefile({
  "def f():",
  "    return 1",
  "",
  "x = 2",
  "# [lma:SleepRib]",
  "y = 3",
  "# [/lma:SleepRib]",
  "",
  "# [lma:threads]",
  '# {"id": "SleepRib", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why 3?\\nsecond line"}',
  '# {"id": "TinOwl", "re": "SleepRib", "span": [0, 3], "author": "BraveFig (Author)", "at": "2026-11-19T19:41:00Z", "body": "because"}',
}, code)
vim.cmd("edit " .. code)
local buf = vim.api.nvim_get_current_buf()
local state = require("lma.state")

-- 1. threads arrive and are drawn
check("threads arrive", wait(8000, function() return state.get(buf) ~= nil end))
watch_errors(buf)
local st = state.get(buf)
check("one thread, two comments", st and #st.threads == 1 and #st.threads[1].comments == 2, st)
local sr, sc, er, ec = state.anchor_range(buf, st.threads[1])
check("anchor covers y = 3", sr == 5 and er == 6, { sr, sc, er, ec })
local concealed = vim.api.nvim_buf_get_extmarks(buf, vim.api.nvim_get_namespaces().lma_conceal, 0, -1, {})
check("both markers concealed", #concealed == 2, concealed)
check("conceallevel raised", vim.wo.conceallevel == 2, vim.wo.conceallevel)
check("thread under cursor on y = 3", state.thread_at(buf, 5, 2) == st.threads[1])
check("no thread on x = 2", state.thread_at(buf, 3, 0) == nil)

-- 2. a comment on a line from the code buffer
vim.api.nvim_win_set_cursor(0, { 2, 4 })
vim.api.nvim_feedkeys(vim.keycode(" ccwhy return 1?<Esc>:w<CR>"), "x", false)
check("comment written into the buffer", wait(8000, function() return text(buf):find("why return 1?", 1, true) ~= nil end), text(buf))
check("two threads now", wait(3000, function() return #state.get(buf).threads == 2 end))
check("draft removed after confirm", wait(3000, function() return #require("lma.drafts").all() == 0 end), require("lma.drafts").all())

-- 3. a visual selection comment
vim.api.nvim_win_set_cursor(0, { 1, 4 })
vim.api.nvim_feedkeys(vim.keycode("vll ccthe name<Esc>:w<CR>"), "x", false)
check("visual comment written", wait(8000, function() return text(buf):find("the name", 1, true) ~= nil end))
wait(3000, function() return #state.get(buf).threads == 3 end)

-- 4. reply from the panel, about part of a comment
vim.api.nvim_feedkeys(vim.keycode(" cp"), "x", false)
local panel_win
for _, w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
  if vim.bo[vim.api.nvim_win_get_buf(w)].filetype == "lmapanel" then panel_win = w end
end
check("panel opens", panel_win ~= nil)
local panel_lines = vim.api.nvim_buf_get_lines(vim.api.nvim_win_get_buf(panel_win), 0, -1, false)
local row
for i, l in ipairs(panel_lines) do if l:find("why 3?", 1, true) then row = i end end
check("panel shows the body", row ~= nil, panel_lines)
vim.api.nvim_set_current_win(panel_win)
-- select "why" (first three chars of the body line)
local col = panel_lines[row]:find("why 3?", 1, true) - 1
vim.api.nvim_win_set_cursor(panel_win, { row, col })
vim.api.nvim_feedkeys(vim.keycode("ll ccabout why<Esc>:w<CR>"), "x", false)
check("reply with span written", wait(8000, function()
  return text(buf):find('"span": [0, 3]', 1, true) ~= nil and text(buf):find("about why", 1, true) ~= nil
end), text(buf):match("# %[lma:threads%].*"))
vim.api.nvim_set_current_win(vim.fn.bufwinid(buf))

-- 5. resolve the thread under the cursor
wait(3000, function() return #state.get(buf).threads[#state.get(buf).threads].comments >= 3 end)
local thread = state.find_comment(buf, "SleepRib")
local r = state.anchor_range(buf, thread)
vim.api.nvim_win_set_cursor(0, { r + 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" cr"), "x", false)
check("resolve written", wait(8000, function() return text(buf):find('"resolves": "SleepRib"', 1, true) ~= nil end))

-- 6. a draft kept by q, offered again
vim.cmd("write")
vim.api.nvim_win_set_cursor(0, { 4, 0 })
vim.api.nvim_feedkeys(vim.keycode(" cckept for later<Esc>q"), "x", false)
check("q keeps a draft", #require("lma.drafts").all() == 1, require("lma.drafts").all())
local offered
vim.ui.select = function(items, opts, on_choice) offered = items; on_choice(items[2]) end
vim.api.nvim_feedkeys(vim.keycode(" cc<Esc>:w<CR>"), "x", false)
check("draft offered", offered and #offered == 2)
check("draft sent", wait(8000, function() return text(buf):find("kept for later", 1, true) ~= nil end))
check("no drafts left", wait(3000, function() return #require("lma.drafts").all() == 0 end))
vim.ui.select = function(items, opts, on_choice) on_choice(items[1]) end

-- 7. a lemon writes the saved file: nvim reloads it on its own
vim.cmd("write")
local before = #errors
local res = lemonaid("comments", "reply", code, "--re", "SleepRib", "--as", "BraveFig (Author)", "lemon reply")
check("lemon reply exits 0", res.code == 0, res.stderr)
check("buffer reloads by itself", wait(5000, function() return text(buf):find("lemon reply", 1, true) ~= nil end))
check("still unmodified", not vim.bo[buf].modified)

-- 8. a comment sent before the reload: refused, reloaded, sent again
local res2 = lemonaid("comments", "reply", code, "--re", "SleepRib", "--as", "BraveFig (Author)", "second lemon reply")
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" ccafter a lemon<Esc>:w<CR>"), "x", false)
check("comment lands after the reload", wait(8000, function() return text(buf):find("after a lemon", 1, true) ~= nil end), { notes = notes, errors = errors })
check("and the lemon's reply too", text(buf):find("second lemon reply", 1, true) ~= nil)

-- 8b. a resolve sent before nvim hears of the lemon's write: refused, reloaded, sent again
vim.cmd("write")
local cli = table.concat({ "lemonaid", "comments", "reply", vim.fn.shellescape(code), "--re", "SleepRib", "--as", "'BraveFig (Author)'", "third", ">/dev/null 2>&1" }, " ")
local before_8b = #errors
os.execute(cli) -- blocks without running nvim's event loop, so the watcher can't reload first
local why_return = state.find_comment(buf, (text(buf):match('"id": "(%w+)", "author": "Caleb Gregory", "at": "[^"]+", "body": "why return 1%?"')))
vim.api.nvim_win_set_cursor(0, { state.anchor_range(buf, why_return) + 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" cr"), "x", false)
check("resolve lands after a refusal", wait(8000, function() return text(buf):find('"resolves": "' .. why_return.root.id .. '"', 1, true) ~= nil end))
local seen = vim.list_slice(errors, before_8b + 1)
check("the server refused it as diverged first", #seen == 1 and seen[1][2] == "diverged", seen)

-- 8c. text chosen before a lemon's write moved it: the comment waits for a new selection
vim.cmd("write")
local notes_before = #notes
vim.api.nvim_win_set_cursor(0, { 4, 0 })
vim.api.nvim_feedkeys(vim.keycode(" cconce more<Esc>"), "x", false)
os.execute(table.concat({ "lemonaid", "comments", "add", vim.fn.shellescape(code), "--lines", "1", "--as", "'BraveFig (Author)'", "moves", ">/dev/null 2>&1" }, " "))
vim.api.nvim_feedkeys(vim.keycode(":w<CR>"), "x", false)
check("comment held for a new selection", wait(8000, function()
  return vim.iter(vim.list_slice(notes, notes_before + 1)):any(function(n) return n:find("select it again", 1, true) ~= nil end)
end), vim.list_slice(notes, notes_before + 1))
check("its draft is kept", #require("lma.drafts").all() == 1)
check("and it wasn't written", text(buf):find("once more", 1, true) == nil)
for _, d in ipairs(require("lma.drafts").all()) do require("lma.drafts").remove(d) end

-- 10. markdown: an inline marker hides in place; a buffer with its own comments keeps its key
local md = work .. "/notes.md"
vim.fn.writefile({
  "# Notes", "", "some <!-- [lma:MossCap] -->words<!-- [/lma:MossCap] --> here", "",
  "<!-- [lma:threads]", '{"id": "MossCap", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "hm"}', "-->",
}, md)
vim.cmd("edit " .. md)
local mdbuf = vim.api.nvim_get_current_buf()
check("markdown threads arrive", wait(8000, function() return state.get(mdbuf) ~= nil end))
local md_conceal = vim.api.nvim_buf_get_extmarks(mdbuf, vim.api.nvim_get_namespaces().lma_conceal, 0, -1, { details = true })
check("two inline markers concealed in place", #md_conceal == 2 and md_conceal[1][4].conceal == "" and md_conceal[2][4].conceal == "", md_conceal)
local sr2, sc2, er2, ec2 = state.anchor_range(mdbuf, state.get(mdbuf).threads[1])
check("markdown anchor is 'words'", table.concat(vim.api.nvim_buf_get_text(mdbuf, sr2, sc2, er2, ec2, {}), "") == "words")

local vault = work .. "/vault.md"
vim.fn.writefile({ "# Vault", "", "a {==claim==}{>>really?<<} here" }, vault)
vim.cmd("badd " .. vault)
vim.b[vim.fn.bufnr(vault)].other_comments = true
vim.cmd("buffer " .. vim.fn.bufnr(vault))
local vbuf = vim.api.nvim_get_current_buf()
wait(5000, function() return #vim.lsp.get_clients({ bufnr = vbuf, name = "lemonaid" }) > 0 end)
wait(300)
vim.api.nvim_feedkeys(vim.keycode(" cc"), "x", false)
check("a buffer with its own comments keeps its comment key", vim.b[vbuf].other_key_pressed == true)
vim.cmd("edit " .. code)

-- 9. editor open shows a file in a split without taking the cursor
vim.cmd("write")
local guide = work .. "/guide.md"
vim.fn.writefile({ "# Guide", "", "line three" }, guide)
local wins_before, cur = #vim.api.nvim_tabpage_list_wins(0), vim.api.nvim_get_current_win()
local opened
vim.system({ "lemonaid", "editor", "open", guide, "--line", "3" }, { text = true }, function(o) opened = o end)
wait(8000, function() return opened ~= nil end)
check("editor open exits 0", opened and opened.code == 0, opened)
check("a split shows the guide", wait(2000, function() return vim.fn.bufwinid(vim.fn.bufnr(guide)) ~= -1 end))
check("cursor stays put", vim.api.nvim_get_current_win() == cur)
check("guide at line 3", vim.api.nvim_win_get_cursor(vim.fn.bufwinid(vim.fn.bufnr(guide)))[1] == 3)

-- 11. a confirmation removes a draft only if it still holds what was sent
local drafts = require("lma.drafts")
local sent_draft = drafts.new(code, "comment", nil, nil, nil)
sent_draft.body = "as sent"
drafts.save(sent_draft)
drafts.sent(sent_draft)
check("a draft with the server isn't offered", #drafts.matching(code, "comment") == 0)
local newer = vim.deepcopy(sent_draft)
newer.body = "changed while it was sent"
drafts.save(newer)
drafts.confirmed(sent_draft)
check("text changed after sending stays", #drafts.all() == 1 and drafts.all()[1].body == "changed while it was sent", drafts.all())
for _, d in ipairs(drafts.all()) do drafts.remove(d) end

-- 12. a change made in the same step as closing the comment window is kept
vim.cmd("edit " .. code)
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" cc<Esc>"), "x", false)
local composer = vim.api.nvim_get_current_win()
local composer_buf = vim.api.nvim_win_get_buf(composer)
vim.api.nvim_buf_set_lines(composer_buf, 0, -1, false, { "written as it closed" })
vim.api.nvim_win_close(composer, true)
check("the last change is kept as a draft", #drafts.all() == 1 and drafts.all()[1].body == "written as it closed", drafts.all())
for _, d in ipairs(drafts.all()) do drafts.remove(d) end

-- 13. only a thread's own markers hide, and one edited into code shows again
local hidden = work .. "/hidden.py"
vim.fn.writefile({
  'EXAMPLE = """',
  "# [lma:Root]",
  '"""',
  "# [lma:Root]",
  "x = 1",
  "# [/lma:Root]",
  "# [lma:Reply]",
  "",
  "# [lma:threads]",
  '# {"id": "Root", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "why?"}',
  '# {"id": "Reply", "re": "Root", "author": "BraveFig (Author)", "at": "2026-11-19T19:41:00Z", "body": "because"}',
}, hidden)
vim.cmd("edit " .. hidden)
local hbuf = vim.api.nvim_get_current_buf()
wait(8000, function() return state.get(hbuf) ~= nil end)
local conceal_ns = vim.api.nvim_get_namespaces().lma_conceal
local hidden_rows = vim.tbl_map(function(m) return m[2] end, vim.api.nvim_buf_get_extmarks(hbuf, conceal_ns, 0, -1, {}))
check("only the thread's two marker lines hide", vim.deep_equal(hidden_rows, { 3, 5 }), hidden_rows)
vim.api.nvim_buf_set_text(hbuf, 3, 0, 3, 0, { "y = 2 " })
-- before the server has answered: the client's own check shows the line
state.refresh_conceal(hbuf)
hidden_rows = vim.tbl_map(function(m) return m[2] end, vim.api.nvim_buf_get_extmarks(hbuf, conceal_ns, 0, -1, {}))
check("a marker line with code typed into it shows", vim.deep_equal(hidden_rows, { 5 }), hidden_rows)
wait(500)
hidden_rows = vim.tbl_map(function(m) return m[2] end, vim.api.nvim_buf_get_extmarks(hbuf, conceal_ns, 0, -1, {}))
check("and stays shown once the server answers", not vim.tbl_contains(hidden_rows, 3), hidden_rows)
vim.cmd("edit!")

-- 14. the watch survives the file going away and coming back
local watched = work .. "/watched.py"
vim.fn.writefile({ "a = 1" }, watched)
vim.cmd("edit " .. watched)
local wbuf = vim.api.nvim_get_current_buf()
wait(5000, function() return state.get(wbuf) ~= nil end)
os.remove(watched)
wait(300)
vim.fn.writefile({ "a = 2" }, watched)
check("a file made again reloads", wait(5000, function() return text(wbuf) == "a = 2" end), text(wbuf))

-- 15. an exclusive selection comments on what nvim selected
local inline = work .. "/inline.md"
vim.fn.writefile({ "abcde" }, inline)
vim.cmd("edit " .. inline)
local ibuf = vim.api.nvim_get_current_buf()
wait(8000, function() return state.get(ibuf) ~= nil end)
vim.o.selection = "exclusive"
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode("v2l ccon ab<Esc>:w<CR>"), "x", false)
check("the comment is on ab", wait(8000, function() return text(ibuf):find("-->ab<!--", 1, true) ~= nil end), text(ibuf))
vim.o.selection = "inclusive"
vim.cmd("write")

-- 16. a reply about part of a comment that has since changed waits for a new selection
local spanned = work .. "/spanned.py"
vim.fn.writefile({
  "# [lma:Root]",
  "x = 1",
  "",
  "# [lma:threads]",
  '# {"id": "Root", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "hello world"}',
}, spanned)
vim.cmd("edit " .. spanned)
local sbuf = vim.api.nvim_get_current_buf()
wait(8000, function() return state.get(sbuf) ~= nil end)
require("lma.panel").close()
vim.api.nvim_feedkeys(vim.keycode(" cp"), "x", false)
local pwin
for _, w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
  if vim.bo[vim.api.nvim_win_get_buf(w)].filetype == "lmapanel" then pwin = w end
end
local plines = vim.api.nvim_buf_get_lines(vim.api.nvim_win_get_buf(pwin), 0, -1, false)
local prow
for i, l in ipairs(plines) do if l:find("hello world", 1, true) then prow = i end end
vim.api.nvim_set_current_win(pwin)
vim.api.nvim_win_set_cursor(pwin, { prow, plines[prow]:find("world", 1, true) - 1 })
local notes_16 = #notes
vim.api.nvim_feedkeys(vim.keycode("ve ccabout world<Esc>"), "x", false)
local reply_win = vim.api.nvim_get_current_win()
check("a reply window opens", vim.api.nvim_buf_get_name(0):find("^lma://comment") ~= nil, vim.list_slice(notes, notes_16 + 1))
vim.api.nvim_buf_set_lines(sbuf, 4, 5, false, { '# {"id": "Root", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "hello there"}' })
check("the server reports the changed body", wait(3000, function()
  local _, root = state.find_comment(sbuf, "Root")
  return root ~= nil and root.body == "hello there"
end))
vim.api.nvim_set_current_win(reply_win)
vim.api.nvim_feedkeys(vim.keycode(":w<CR>"), "x", false)
check("the reply waits for a new selection", wait(5000, function()
  return vim.iter(vim.list_slice(notes, notes_16 + 1)):any(function(n) return n:find("no longer says", 1, true) ~= nil end)
end), vim.list_slice(notes, notes_16 + 1))
check("and wasn't written", text(sbuf):find("about world", 1, true) == nil)
for _, d in ipairs(drafts.all()) do drafts.remove(d) end

-- 16b. the same, sent before the client hears of the change: the server checks the quote
vim.api.nvim_buf_set_lines(sbuf, 4, 5, false, { '# {"id": "Root", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "hello world"}' })
wait(3000, function() local _, root = state.find_comment(sbuf, "Root"); return root and root.body == "hello world" end)
pwin = nil
for _, w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
  if vim.bo[vim.api.nvim_win_get_buf(w)].filetype == "lmapanel" then pwin = w end
end
plines = vim.api.nvim_buf_get_lines(vim.api.nvim_win_get_buf(pwin), 0, -1, false)
for i, l in ipairs(plines) do if l:find("hello world", 1, true) then prow = i end end
vim.api.nvim_set_current_win(pwin)
vim.api.nvim_win_set_cursor(pwin, { prow, plines[prow]:find("world", 1, true) - 1 })
local notes_16b = #notes
vim.api.nvim_feedkeys(vim.keycode("ve ccabout world again<Esc>"), "x", false)
reply_win = vim.api.nvim_get_current_win()
vim.api.nvim_buf_set_lines(sbuf, 4, 5, false, { '# {"id": "Root", "author": "Caleb Gregory", "at": "2026-11-19T19:40:00Z", "body": "hello there"}' })
vim.api.nvim_set_current_win(reply_win)
vim.api.nvim_feedkeys(vim.keycode(":w<CR>"), "x", false)
check("the server refuses a reply whose quote changed", wait(5000, function()
  return vim.iter(vim.list_slice(notes, notes_16b + 1)):any(function(n) return n:find("no longer says", 1, true) ~= nil end)
end), vim.list_slice(notes, notes_16b + 1))
wait(500)
check("and it wasn't written either", text(sbuf):find("about world again", 1, true) == nil)
for _, d in ipairs(drafts.all()) do drafts.remove(d) end

-- 17. Enter in the panel jumps to the thread
pwin = nil
for _, w in ipairs(vim.api.nvim_tabpage_list_wins(0)) do
  if vim.bo[vim.api.nvim_win_get_buf(w)].filetype == "lmapanel" then pwin = w end
end
vim.api.nvim_set_current_win(pwin)
vim.api.nvim_win_set_cursor(pwin, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode("<CR>"), "x", false)
check("Enter jumps to the anchor", vim.api.nvim_get_current_buf() == sbuf and vim.api.nvim_win_get_cursor(0)[1] == 2,
  { vim.api.nvim_get_current_buf(), vim.api.nvim_win_get_cursor(0) })
vim.cmd("edit!")

-- 18. editor open on the file you are in leaves your cursor alone
vim.api.nvim_win_set_cursor(0, { 1, 0 })
local reopened
vim.system({ "lemonaid", "editor", "open", spanned, "--line", "2" }, { text = true }, function(o) reopened = o end)
wait(8000, function() return reopened ~= nil end)
wait(300)
check("the cursor stays on line 1", vim.api.nvim_win_get_cursor(0)[1] == 1 and vim.api.nvim_get_current_buf() == sbuf)


-- 19. a draft open in one comment window isn't offered to another
vim.cmd("edit " .. code)
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" ccstill writing<Esc>"), "x", false)
local first_window = vim.api.nvim_get_current_win()
check("the first window's draft is saved", #drafts.all() == 1)
vim.api.nvim_set_current_win(vim.fn.bufwinid(vim.fn.bufnr(code)))
local offered_19
vim.ui.select = function(items, _, on_choice) offered_19 = items; on_choice(items[1]) end
vim.api.nvim_feedkeys(vim.keycode(" cc<Esc>"), "x", false)
check("it isn't offered while that window has it", offered_19 == nil, offered_19)
vim.api.nvim_win_close(vim.api.nvim_get_current_win(), true)
vim.api.nvim_win_close(first_window, true)
check("closing it keeps its text", #drafts.all() == 1 and drafts.all()[1].body == "still writing", drafts.all())
local again = drafts.all()[1]
check("and frees it to be offered", drafts.claim(again) and not drafts.claim(again))
drafts.release(again)
for _, d in ipairs(drafts.all()) do drafts.remove(d) end

-- 20. a notification about an older buffer hides nothing that isn't its marker now
local stale = work .. "/stale.py"
vim.fn.writefile({ "y = 2", "x = 1" }, stale)
vim.cmd("edit " .. stale)
local stbuf = vim.api.nvim_get_current_buf()
wait(5000, function() return state.get(stbuf) ~= nil end)
require("lma").on_threads(nil, {
  uri = vim.uri_from_bufnr(stbuf), version = 1,
  threads = { {
    anchor = { start = { line = 1, character = 0 }, ["end"] = { line = 1, character = 5 } },
    markers = { { range = { start = { line = 0, character = 0 }, ["end"] = { line = 1, character = 0 } }, text = "# [lma:Root]\n" } },
    comments = { { id = "Root", author = "Caleb Gregory", at = "2026-11-19T19:40:00Z", body = "why?", resolved = false, depth = 0, re = vim.NIL, span = vim.NIL } },
  } },
}, { client_id = vim.lsp.get_clients({ bufnr = stbuf, name = "lemonaid" })[1].id })
check("code where a marker was isn't hidden", #vim.api.nvim_buf_get_extmarks(stbuf, conceal_ns, 0, -1, {}) == 0)

-- 21. a one-character exclusive selection is that character
local one = work .. "/one.md"
vim.fn.writefile({ "abcde" }, one)
vim.cmd("edit " .. one)
local obuf = vim.api.nvim_get_current_buf()
wait(8000, function() return state.get(obuf) ~= nil end)
vim.o.selection = "exclusive"
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode("v ccon a<Esc>:w<CR>"), "x", false)
check("the comment is on a", wait(8000, function() return text(obuf):find("-->a<!--", 1, true) ~= nil end), text(obuf))
wait(3000, function() return #require("lma.drafts").all() == 0 end) -- removed once the server answers
vim.o.selection = "inclusive"

-- 22. a list of drafts opened before another window saved a draft opens the saved one
vim.cmd("edit " .. code)
-- keyed by the buffer's name, as the client keys it (nvim resolves /tmp to /private/tmp)
local listed = drafts.new(vim.api.nvim_buf_get_name(0), "comment", nil, nil, nil)
listed.body = "old draft"
drafts.save(listed)
local choosers = {}
vim.ui.select = function(items, _, on_choice) choosers[#choosers + 1] = { items = items, choose = on_choice } end
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" cc"), "x", false)
vim.api.nvim_feedkeys(vim.keycode(" cc"), "x", false)
check("two lists are open", #choosers == 2)
choosers[1].choose(choosers[1].items[2])
vim.cmd("stopinsert")
vim.api.nvim_buf_set_lines(0, 0, -1, false, { "newer saved draft" })
vim.api.nvim_win_close(0, true)
choosers[2].choose(choosers[2].items[2])
vim.cmd("stopinsert")
check("the second list opens the newer text", vim.api.nvim_buf_get_lines(0, 0, -1, false)[1] == "newer saved draft",
  vim.api.nvim_buf_get_lines(0, 0, -1, false))
vim.api.nvim_win_close(0, true)
check("and closing it keeps the newer text", drafts.all()[1] and drafts.all()[1].body == "newer saved draft", drafts.all())

-- 23. clearing a draft and writing drops it and lets it go
vim.ui.select = function(items, _, on_choice) on_choice(items[2]) end
vim.api.nvim_feedkeys(vim.keycode(" cc"), "x", false)
vim.cmd("stopinsert")
vim.api.nvim_buf_set_lines(0, 0, -1, false, { "" })
vim.api.nvim_feedkeys(vim.keycode(":w<CR>"), "x", false)
wait(200)
check("the cleared draft is gone", #drafts.all() == 0, drafts.all())
check("and not held", drafts.claim(listed))
drafts.release(listed)
vim.ui.select = function(items, _, on_choice) on_choice(items[1]) end

-- 24. a selection covers what a yank of it takes, line breaks included
local yanked = vim.api.nvim_create_buf(true, true)
vim.api.nvim_set_current_buf(yanked)
vim.api.nvim_buf_set_lines(yanked, 0, -1, false, { "abcde", "fgh", "", "xéz" })
local taken
vim.keymap.set("x", "<F9>", function()
  local sr, sc, er, ec = require("lma.selection").take(yanked)
  taken = table.concat(vim.api.nvim_buf_get_text(yanked, sr, sc, er, ec, {}), "\n")
end, { buffer = yanked })
local mismatches = {}
for _, sel in ipairs({ "inclusive", "exclusive" }) do
  vim.o.selection = sel
  for _, case in ipairs({ { 1, 0, "vj" }, { 1, 0, "v$" }, { 1, 2, "vjj" }, { 2, 0, "vj" }, { 1, 0, "v" },
      { 4, 0, "vl" }, { 1, 0, "vjl" }, { 4, 1, "v" }, { 3, 0, "vj" }, { 3, 0, "v" }, { 2, 0, "vj" },
      { 4, 2, "vk" } }) do
    vim.api.nvim_win_set_cursor(0, { case[1], case[2] })
    vim.api.nvim_feedkeys(vim.keycode(case[3] .. "<F9>"), "x", false)
    vim.api.nvim_win_set_cursor(0, { case[1], case[2] })
    vim.fn.setreg('"', "")
    vim.api.nvim_feedkeys(vim.keycode(case[3] .. "y"), "x", false)
    if taken ~= vim.fn.getreg('"') then
      mismatches[#mismatches + 1] = { sel, case[3], taken = taken, yank = vim.fn.getreg('"') }
    end
  end
end
vim.o.selection = "inclusive"
check("selections match yanks", #mismatches == 0, mismatches)
vim.o.selection = "old"
vim.api.nvim_win_set_cursor(0, { 1, 0 })
local refused_old
vim.keymap.set("x", "<F8>", function() refused_old = require("lma.selection").take(yanked) == nil end, { buffer = yanked })
vim.api.nvim_feedkeys(vim.keycode("vl<F8>"), "x", false)
vim.o.selection = "inclusive"
check("'selection' old refuses a characterwise selection", refused_old == true)

-- 25. another nvim sharing the state directory: its drafts get other ids, and a draft
-- it holds isn't ours to take
local other_nvim = { "nvim", "--headless", "--clean", "--cmd", "set rtp^=" .. vim.fn.fnameescape(plugin) }
-- two fresh nvims at once, as two editors started together would be
local first_id = vim.list_extend(vim.deepcopy(other_nvim), {
  "-c", "lua io.stdout:write(require('lma.drafts').new('/x', 'comment').id)", "-c", "qa!" })
local one_nvim, two_nvim = vim.system(first_id, { text = true }), vim.system(first_id, { text = true })
local one_id, two_id = one_nvim:wait().stdout, two_nvim:wait().stdout
check("ids differ between nvims", one_id ~= "" and one_id ~= two_id, { one_id, two_id })
local shared = drafts.new(vim.api.nvim_buf_get_name(0), "comment")
shared.body = "held elsewhere"
drafts.save(shared)
local holding = vim.system(vim.list_extend(vim.deepcopy(other_nvim), {
  "-c", ("lua local d = require('lma.drafts'); d.claim({ id = %q }); vim.wait(4000)"):format(shared.id), "-c", "qa!" }))
wait(3000, function() return #drafts.matching(shared.path, "comment") == 0 end)
check("a draft another nvim holds can't be taken", drafts.claim(shared) == false)
check("nor is it offered", #drafts.matching(shared.path, "comment") == 0)
holding:wait()
check("once that nvim exits, it can", drafts.claim(shared) == true)
drafts.release(shared)
drafts.remove(shared)

-- an nvim killed while it holds a draft doesn't keep it held
local killed = drafts.new(vim.api.nvim_buf_get_name(0), "comment")
killed.body = "held by a crash"
drafts.save(killed)
local crashing = vim.system(vim.list_extend(vim.deepcopy(other_nvim), {
  "-c", ("lua require('lma.drafts').claim({ id = %q }); vim.wait(30000)"):format(killed.id) }))
-- not offered once the other nvim holds it (claiming here to find out would take it)
wait(3000, function()
  return not vim.iter(drafts.matching(killed.path, "comment")):any(function(d) return d.id == killed.id end)
end)
check("held while that nvim runs", drafts.claim(killed) == false)
crashing:kill(9)
crashing:wait()
check("free once it is killed", drafts.claim(killed) == true)
drafts.release(killed)
drafts.remove(killed)

-- 25b. clearing the text in an open comment window and typing again keeps the draft held
vim.cmd("edit " .. code)
vim.api.nvim_win_set_cursor(0, { 1, 0 })
vim.api.nvim_feedkeys(vim.keycode(" ccfirst text<Esc>"), "x", false)
local live = vim.api.nvim_get_current_buf()
local live_id = drafts.all()[1].id
vim.api.nvim_buf_set_lines(live, 0, -1, false, { "" })
vim.api.nvim_exec_autocmds("TextChanged", { buffer = live })
vim.api.nvim_buf_set_lines(live, 0, -1, false, { "second text" })
vim.api.nvim_exec_autocmds("TextChanged", { buffer = live })
local contender = vim.system(vim.list_extend(vim.deepcopy(other_nvim), {
  "-c", ("lua io.stdout:write(tostring(require('lma.drafts').claim({ id = %q })))"):format(live_id), "-c", "qa!" }), { text = true }):wait()
check("another nvim can't claim it after a clear", contender.stdout == "false", contender.stdout)
vim.api.nvim_win_close(0, true)
for _, d in ipairs(drafts.all()) do drafts.remove(d) end

-- 26. a confirmed draft stays held until its file is gone
local confirming = drafts.new(vim.api.nvim_buf_get_name(0), "comment")
confirming.body = "sent"
drafts.save(confirming)
drafts.claim(confirming)
drafts.sent(confirming)
local draft_file = vim.fn.stdpath("state") .. "/lma/drafts/" .. confirming.id .. ".json"
local real_close, closes = vim.uv.fs_close, {}
vim.uv.fs_close = function(fd, ...)
  closes[#closes + 1] = vim.fn.filereadable(draft_file) == 1
  return real_close(fd, ...)
end
drafts.confirmed(confirming)
vim.uv.fs_close = real_close
check("the lock goes only after the draft", #closes > 0 and not vim.tbl_contains(closes, true), closes)
end

-- a script error must still write the results and quit, or nvim waits for input
local ran, problem = xpcall(run, debug.traceback)
check("the script ran to the end", ran, problem)
results[#results + 1] = ("%d failed"):format(failed)
vim.fn.writefile(results, work .. "/results.txt")
vim.cmd("qa!")
