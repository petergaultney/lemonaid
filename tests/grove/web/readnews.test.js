// A lemon's page's record of what it has marked read (src/lemonaid/grove/web/readnews.js), run by `node --test`.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/readnews.js"), "utf8");
const context = {};
context.window = context;
vm.runInNewContext(script, context);

test("a report is marked read once, so a refresh doesn't undo a lemon marked unread by hand", () => {
  const read = context.groveReadNews();

  assert.equal(read.due(10), true);
  read.done(10);
  assert.equal(read.due(10), false);
});

test("a newer report is marked read, and one that failed to send is tried again", () => {
  const read = context.groveReadNews();
  read.done(10);

  assert.equal(read.due(20), true);
  assert.equal(read.due(20), true);
});
