-- Comments you have written but the server hasn't confirmed, one JSON file each in nvim's
-- state directory, so a refusal, a closed window or nvim exiting never loses one.
--
--   { id, path, kind = "comment" | "reply", re, span, quote, body, updated }
--
-- `quote` is the text of its parent that a reply's `span` covered when you chose it.

local M = {}

-- Drafts in use, by id: open in a comment window ({ open = true }), or with the server
-- ({ sent = <the body sent> }).  One in use is not offered again, so two windows never
-- write the same draft.  Another nvim may share the state directory, so a draft in use
-- also holds an advisory lock (flock) on its lock file.  Taking one is atomic, and the
-- system lets go of it when its nvim exits, however it exits, so no lock is left behind.
local held = {}

local ffi = require("ffi")
pcall(ffi.cdef, "int flock(int fd, int operation);")
local LOCK_EX, LOCK_NB = 2, 4

-- The open lock file of each draft this nvim holds; closing it lets go of the lock.
local lock_fds = {}

local function dir()
  return vim.fn.stdpath("state") .. "/lma/drafts"
end

local function file(id)
  return dir() .. "/" .. id .. ".json"
end

local function lock_file(id)
  return dir() .. "/" .. id .. ".lock"
end

-- Takes the draft's lock; false if another nvim (or another window here) holds it.
local function lock(id)
  vim.fn.mkdir(dir(), "p")
  local fd = vim.uv.fs_open(lock_file(id), "a", 384) -- 0600
  if not fd then return false end
  if ffi.C.flock(fd, LOCK_EX + LOCK_NB) ~= 0 then
    vim.uv.fs_close(fd)
    return false
  end
  lock_fds[id] = fd
  return true
end

local function unlock(id)
  local fd = lock_fds[id]
  lock_fds[id] = nil
  if fd then vim.uv.fs_close(fd) end
end

local function locked_elsewhere(id)
  if lock_fds[id] or vim.fn.filereadable(lock_file(id)) == 0 then return false end
  local fd = vim.uv.fs_open(lock_file(id), "r", 384)
  if not fd then return false end
  local busy = ffi.C.flock(fd, LOCK_EX + LOCK_NB) ~= 0
  vim.uv.fs_close(fd) -- lets go of it at once if we got it
  return busy
end

local function read(path)
  local ok, draft = pcall(function() return vim.json.decode(table.concat(vim.fn.readfile(path), "\n")) end)
  return ok and type(draft) == "table" and draft.id and draft or nil
end

function M.new(path, kind, re, span, quote)
  -- unique across nvims sharing the state directory (the pid) and within one (the clock)
  local id = ("%d-%d-%d"):format(os.time(), vim.fn.getpid(), vim.uv.hrtime())
  return { id = id, path = path, kind = kind, re = re, span = span, quote = quote, body = "" }
end

-- Written beside the draft and renamed over it, so an interrupted save leaves the last
-- one whole.  Says so when it can't save.
function M.save(draft)
  draft.updated = os.time()
  local path = file(draft.id)
  local partial = path .. ".partial"
  local ok, err = pcall(function()
    vim.fn.mkdir(dir(), "p")
    assert(vim.fn.writefile({ vim.json.encode(draft) }, partial) == 0, "can't write " .. partial)
    assert(os.rename(partial, path))
  end)
  if not ok then
    vim.notify("lma: couldn't save your draft: " .. tostring(err), vim.log.levels.ERROR)
  end
  return ok
end

-- Deletes the saved text.  The lock file stays, since a window that still has the draft
-- may save it again (you cleared the text and kept typing), and its lock must stay the
-- one other nvims find.
function M.remove(draft)
  os.remove(file(draft.id))
end

-- Deletes a draft that is done with, sent or dropped, and its lock file.  Called holding
-- its lock: an nvim that opened the old lock file meanwhile finds no draft once it gets
-- the lock (claim_saved reads after locking).
function M.retire(draft)
  os.remove(file(draft.id))
  os.remove(lock_file(draft.id))
end

-- Takes the draft for a comment window; false if it is in use already.
function M.claim(draft)
  if held[draft.id] or not lock(draft.id) then return false end
  held[draft.id] = { open = true }
  return true
end

-- Takes a draft chosen from a list for a comment window, as it is saved now: the list
-- may be older than another window's last save.  nil, and why, when it is in use or gone
-- (sent or dropped since the list was made).
function M.claim_saved(draft)
  if held[draft.id] or not lock(draft.id) then return nil, "that draft is open in another window" end
  local saved = read(file(draft.id))
  if saved == nil then
    unlock(draft.id)
    return nil, "that draft was sent or dropped meanwhile"
  end
  held[draft.id] = { open = true }
  return saved
end

-- The window closed without sending.
function M.release(draft)
  held[draft.id] = nil
  unlock(draft.id)
end

function M.sent(draft)
  held[draft.id] = { sent = draft.body }
end

-- The server wrote the comment: remove the draft, unless you have changed it since it
-- was sent, in which case what you wrote since stays.
function M.confirmed(draft)
  local sent_body = held[draft.id] and held[draft.id].sent
  -- still holding it, so no other window or nvim can open it between the check and the
  -- removal
  local saved = read(file(draft.id))
  if saved == nil or saved.body == sent_body then M.retire(draft) end
  M.release(draft)
end

-- The server didn't write it: it can be offered again.
function M.returned(draft)
  M.release(draft)
end

function M.all()
  local drafts = {}
  for _, path in ipairs(vim.fn.glob(dir() .. "/*.json", false, true)) do
    drafts[#drafts + 1] = read(path)
  end
  table.sort(drafts, function(a, b) return (a.updated or 0) > (b.updated or 0) end)
  return drafts
end

-- The drafts for the same kind of comment on the same file, and for a reply, to the
-- same comment; newest first, leaving out those in use.
function M.matching(path, kind, re)
  return vim.tbl_filter(function(draft)
    return held[draft.id] == nil and not locked_elsewhere(draft.id) and draft.path == path and draft.kind == kind
      and (kind ~= "reply" or draft.re == re)
  end, M.all())
end

return M
