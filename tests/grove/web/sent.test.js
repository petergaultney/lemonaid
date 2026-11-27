// A lemon's page's sent messages (src/lemonaid/grove/web/sent.js), run by `node --test`.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/sent.js"), "utf8");
const context = {Date};
context.window = context;
vm.runInNewContext(script, context);
const {matching, unrecorded, inTime} = context.groveSent;

const order = (items, sent) => Array.from(inTime(items, sent), ([, html]) => html);  // in this realm, for deepEqual
const you = text => ({role: "user", text, at: "2026-11-27T18:44:08Z"});
const logs = Array.from({length: 200}, (_, i) => `2026-11-27 10:47 - line ${i} of a long paste`).join("\n");

test("a message recorded whole, or inside a wrapper, counts", () => {
  assert.equal(matching("hello", [you("hello")]), 1);
  assert.equal(matching("  hello\n", [you("[from the web] hello")]), 1);
  assert.equal(matching("hello", [{role: "lemon", text: "hello"}]), 0);
});

test("a long message the conversation recorded cut short counts", () => {
  const cut = `${logs.slice(0, 4000)}\n...(truncated)...`;
  assert.equal(matching(logs, [you(cut)]), 1);
  assert.equal(matching(`${logs} and more`, [you(cut)]), 1);
});

test("a cut-short record of a different message doesn't count", () => {
  const cut = `${logs.slice(0, 4000)}\n...(truncated)...`;
  assert.equal(matching(`other ${logs}`, [you(cut)]), 0);
  assert.equal(matching("2026", [you(cut)]), 0);
});

test("a record cut short to whitespace, or a short message ending in the marker, is no cut", () => {
  assert.equal(matching("unrecorded", [you(`${" ".repeat(8000)}\n...(truncated)...`)]), 0);
  assert.equal(matching("hello world", [you("hello\n...(truncated)...")]), 0);
  assert.equal(matching("hello\n...(truncated)...", [you("hello\n...(truncated)...")]), 1);
});

const texts = list => Array.from(list, p => p.text);  // in this realm, for deepEqual
const cut = `${logs.slice(0, 4000)}\n...(truncated)...`;

test("one record clears only the oldest of two sends it could be", () => {
  const first = {text: `${logs} first`, seen: 0}, second = {text: `${logs} second`, seen: 0};
  const left = unrecorded([first, second], [you(cut)]);
  assert.deepEqual(texts(left), [second.text]);
  assert.deepEqual(texts(unrecorded(left, [you(cut)])), [second.text]);
  assert.deepEqual(texts(unrecorded(left, [you(cut), you(cut)])), []);
});

test("a send waits for a record after those that held its text when it was sent", () => {
  const p = {text: "again", seen: 1};
  assert.deepEqual(texts(unrecorded([p], [you("again")])), ["again"]);
  assert.deepEqual(texts(unrecorded([p], [you("again"), you("again")])), []);
});

test("a sent message goes before the first entry later than it", () => {
  const items = [["2026-11-27T18:40:00Z", "a"], ["2026-11-27T18:56:40Z", "b"], ["2026-11-27T18:57:00Z", "c"]];
  const sent = [["2026-11-27T18:44:08Z", "sent"]];
  assert.deepEqual(order(items, sent), ["a", "sent", "b", "c"]);
});

test("sent messages after every entry, or before all of them, keep their own order", () => {
  const items = [["2026-11-27T18:40:00Z", "a"]];
  const sent = [["2026-11-27T18:50:00Z", "late2"], ["2026-11-27T18:45:00Z", "late1"], ["2026-11-27T18:00:00Z", "early"]];
  assert.deepEqual(order(items, sent), ["early", "a", "late1", "late2"]);
});

test("an entry without a time stays in its place", () => {
  const items = [["2026-11-27T18:40:00Z", "a"], ["", "untimed"], ["2026-11-27T18:50:00Z", "b"]];
  const sent = [["2026-11-27T18:45:00Z", "sent"]];
  assert.deepEqual(order(items, sent), ["a", "untimed", "sent", "b"]);
});
