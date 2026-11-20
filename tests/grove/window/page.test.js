// The page's search and dialog keys (src/lemonaid/grove/window/static/page.html), run by `node --test`
// against the page's own functions with stand-ins for Python and the DOM.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const page = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/page.html"), "utf8");
const keys = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/keys.js"), "utf8");
const source = name => page.match(new RegExp(`function ${name}\\([^]*?\\n\\}`))[0];

function searching() {
  const replies = [];
  const context = {
    search: {text: "", found: [], chosen: 0}, searchAsked: 0, zoomed: null, DATA: {blocks: []},
    draw: () => {}, goTo: () => {}, jumpTo: () => {}, module: undefined,
    window: {pywebview: {api: {search: () => new Promise(resolve => replies.push(resolve))}}},
  };
  vm.createContext(context);
  vm.runInContext(`${keys}\n${source("openSearch")}\n${source("searchKey")}`, context);
  return {context, replies};
}

test("choosing among matches, or an ignored key, while Python answers keeps the answer", async () => {
  for (const key of ["ArrowDown", "Shift"]) {
    const {context, replies} = searching();

    vm.runInContext("searchKey({key: 'a'})", context);
    vm.runInContext(`searchKey({key: '${key}'})`, context);
    replies[0]([{digit: "1"}]);
    await new Promise(setImmediate);
    assert.equal(context.search.found.length, 1, `${key} lost the search's answer`);
  }
});

test("an answer to text since changed is dropped", async () => {
  const {context, replies} = searching();

  vm.runInContext("searchKey({key: 'a'}); searchKey({key: 'b'})", context);
  replies[0]([{digit: "1"}, {digit: "2"}]);
  await new Promise(setImmediate);
  assert.equal(context.search.found.length, 0);
  replies[1]([{digit: "1"}]);
  await new Promise(setImmediate);
  assert.equal(context.search.found.length, 1);
});

test("Escape closes a dialog that has no field to take it", () => {
  const closed = [];
  const context = {dialogOpen: () => true, closeMenus: () => closed.push(true)};
  vm.createContext(context);
  vm.runInContext(source("onKey"), context);

  vm.runInContext("onKey({key: 'Escape', preventDefault() {}})", context);
  vm.runInContext("onKey({key: 'x', preventDefault() {}})", context);
  assert.equal(closed.length, 1);
});

test("an answer for a search closed since doesn't reach the next one", async () => {
  const {context, replies} = searching();

  vm.runInContext("searchKey({key: 'a'}); searchKey({key: 'Escape'}); openSearch()", context);
  replies[0]([{digit: "1"}]);
  await new Promise(setImmediate);
  assert.equal(context.search.found.length, 0);
});

const menuJs = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/menu.js"), "utf8");
const fromMenu = name => menuJs.match(new RegExp(`function ${name}\\([^]*?\\n\\}`))[0];
const lemon = (channel, name) => ({channel, name, session: name});

function choosing() {
  const shown = [];
  const block = {digit: "2", group: "lemonaid", trees: [
    {key: "ant", letter: "a", label: "ant", lemons: [lemon("c:1", "one"), lemon("c:2", "two")]},
    {key: "bee", letter: "b", label: "bee", lemons: [lemon("c:3", "three")]},
  ]};
  const context = {
    selecting: {mode: ""}, zoomed: "2", DATA: {blocks: [block]}, module: undefined,
    draw: () => {}, status: () => {}, said: () => {}, back: () => {}, zoomTo: () => {},
    menuBeside: target => shown.push(target),
  };
  vm.createContext(context);
  vm.runInContext(`${keys}\n${fromMenu("selectKey")}`, context);
  const type = (...ks) => ks.forEach(k => vm.runInContext(`selectKey({key: ${JSON.stringify(k)}})`, context));
  return {context, shown, type};
}

test("tab's keys choose a tree's first lemon, another lemon, the whole tree, or the block", () => {
  const {shown, type} = choosing();

  type("a");
  type(".", "a", "1");
  type("$", "b");
  type("#");
  assert.deepEqual(shown.map(t => [t.key, t.channel, !!t.block]), [["ant", "c:1", false], ["ant", "c:2", false], ["bee", "", false], ["", "", true]]);
});

test("a block's menu only recolors it, and a lemon's or a tree's never does", () => {
  const context = {EDITS: null};
  vm.createContext(context);
  vm.runInContext(`${menuJs.match(/const EDITS = [^\n]*/)[0]}\nconst editsFor = ${menuJs.match(/const editsFor = ([^\n]*)/)[1]}`, context);

  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(editsFor({block: true}).map(e => e[0]))", context)), ["color"]);
  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(editsFor({}).map(e => e[0]))", context)), ["rename", "snooze", "archive", "pin", "group"]);
});

test("tab's digits build a block's number, so 1 then 2 chooses in block 12", () => {
  const shown = [];
  const block = digit => ({digit, group: `g${digit}`, trees: [{key: `t${digit}`, letter: "a", label: "a", lemons: [lemon(`c:${digit}`, digit)]}]});
  const context = {
    selecting: {mode: ""}, zoomed: null, typed: "", DATA: {blocks: [block("1"), block("2"), block("12")]}, module: undefined,
    draw: () => {}, status: () => {}, said: () => {}, back: () => {}, menuBeside: target => shown.push(target),
  };
  context.zoomTo = d => { context.zoomed = d; };
  vm.createContext(context);
  vm.runInContext(`${keys}\n${fromMenu("selectKey")}`, context);

  for (const k of ["1", "2", "a"]) vm.runInContext(`selectKey({key: ${JSON.stringify(k)}})`, context);
  assert.equal(shown[0].channel, "c:12");
  for (const k of ["2", "a"]) vm.runInContext(`selectKey({key: ${JSON.stringify(k)}})`, context);
  assert.equal(shown[1].channel, "c:2");  // a letter in between starts the number afresh
});

test("backspace in select mode backs out to where it began, then leaves it", () => {
  for (const [from, path] of [[null, [null, "leave"]], ["2", ["leave"]], ["1", ["1", "leave"]]]) {
    const context = {selecting: {mode: ""}, selectFrom: from, zoomed: "2", DATA: {blocks: [{digit: "1"}, {digit: "2"}]}, draw: () => {}};
    context.goTo = d => { context.zoomed = d; };
    vm.createContext(context);
    vm.runInContext(fromMenu("selectKey"), context);
    const seen = [];
    for (let i = 0; i < path.length; i++) {
      vm.runInContext("selectKey({key: 'Backspace'})", context);
      seen.push(context.selecting ? context.zoomed : "leave");
    }
    assert.deepEqual(seen, path, `select mode begun in ${from}`);
  }
});

test("a block number backed out of with backspace doesn't begin the next one", () => {
  const shown = [];
  const block = digit => ({digit, group: `g${digit}`, trees: [{key: `t${digit}`, letter: "a", label: "a", lemons: [lemon(`c:${digit}`, digit)]}]});
  const context = {
    selecting: {mode: ""}, selectFrom: null, zoomed: null, typed: "", DATA: {blocks: [block("1"), block("2"), block("12")]}, module: undefined,
    draw: () => {}, status: () => {}, said: () => {}, back: () => {}, menuBeside: target => shown.push(target),
  };
  context.zoomTo = context.goTo = d => { context.zoomed = d; };
  vm.createContext(context);
  vm.runInContext(`${keys}\n${fromMenu("selectKey")}`, context);

  for (const k of ["1", "Backspace", "2", "a"]) vm.runInContext(`selectKey({key: ${JSON.stringify(k)}})`, context);
  assert.equal(shown[0].channel, "c:2");
});
