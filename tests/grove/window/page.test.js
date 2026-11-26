// The page's search and dialog keys (src/lemonaid/grove/window/static/page.html), run by `node --test`
// against the page's own functions with stand-ins for Python and the DOM.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const page = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/page.html"), "utf8");
const keys = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/keys.js"), "utf8");
const {shownKey} = require("../../../src/lemonaid/grove/window/static/layout.js");
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

test("a block's menu recolors it and changes its number, block 0's gives back its home group's, and a lemon's or a tree's does neither", () => {
  const context = {EDITS: null};
  vm.createContext(context);
  const line = name => menuJs.match(new RegExp(`const ${name} = [^\\n]*`))[0];
  vm.runInContext(`${line("EDITS")}\n${line("BLOCK_EDITS")}\n${line("HOME_EDITS")}\nconst editsFor = ${menuJs.match(/const editsFor = ([^\n]*)/)[1]}`, context);

  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(editsFor({block: true}).map(e => e[0]))", context)), ["color", "earlier", "later", "home"]);
  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(editsFor({block: true, home: true}).map(e => e[0]))", context)), ["home"]);
  assert.deepEqual(JSON.parse(vm.runInContext("JSON.stringify(editsFor({}).map(e => e[0]))", context)), ["rename", "snooze", "archive", "pin", "group", "graft"]);
});

test("an edit's letter chooses it from the menu with or without Shift", () => {
  const chosen = [];
  const context = {menu: {style: {}}, menuTarget: {}, menuAt: 0, drawMenu: () => {}, begin: action => chosen.push(action)};
  vm.createContext(context);
  vm.runInContext(`${menuJs.match(/const EDITS = [^\n]*/)[0]}\nvar menuItems = EDITS;\n${fromMenu("choose")}\n${fromMenu("menuKey")}`, context);

  for (const key of ["t", "T", "R", "x"]) vm.runInContext(`menuKey({key: ${JSON.stringify(key)}})`, context);
  assert.deepEqual(chosen, ["graft", "graft", "rename"]);
});

// The graft dialog, with stand-ins for its field and its trees, and the trees Enter sent to Python.
async function grafting(trees) {
  const sent = [];
  const element = () => ({style: {}, dataset: {}, classList: {on: false, toggle(_, on) { this.on = on; }}, addEventListener() {}, scrollIntoView() {}});
  const input = {...element(), value: "", focus() {}, select() {}};
  const items = trees.map(([value, label]) => ({...element(), dataset: {value}, textContent: label}));
  const dialog = {style: {}, querySelector: () => input, querySelectorAll: () => items};
  const context = {
    dialog, dialogOpen: () => true, closeMenus: () => {}, said: () => {},
    window: {pywebview: {api: {edit_info: async () => ({what: "Put it on another lemon's tree", trees, presets: [], groups: []}), edit: async (...args) => sent.push(args[4])}}},
  };
  vm.createContext(context);
  vm.runInContext(`${menuJs.match(/const escaped = [^\n]*/)[0]}\n${fromMenu("edit")}\nasync ${fromMenu("begin")}`, context);
  await context.begin("graft", {digit: "5", key: "g", channel: "c:1"});
  const press = key => dialog.onkeydown({key, preventDefault() {}, stopPropagation() {}});
  const type = text => { input.value = text; input.oninput(); };
  const on = () => items.filter(item => item.classList.on).map(item => item.dataset.value);
  return {sent, press, type, on};
}

test("the graft dialog marks the tree Enter picks, and arrows move the mark among those the typing leaves", async () => {
  const {sent, press, type, on} = await grafting([["c:a", "5a ant"], ["c:b", "5b bee"], ["c:c", "6a bear"]]);

  assert.deepEqual(on(), ["c:a"]);
  press("ArrowUp");
  assert.deepEqual(on(), ["c:c"]);
  type("be");
  assert.deepEqual(on(), ["c:b"]);
  press("ArrowDown");
  assert.deepEqual(on(), ["c:c"]);
  press("Enter");
  assert.deepEqual(sent, ["c:c"]);
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

test("a lemon with a jump problem still asks Python, which may resume it", () => {
  const asked = [];
  const context = {
    hideCard: () => {}, wholeGrove: () => {}, draw: () => {}, document: {getElementById: () => ({})},
    window: {pywebview: {api: {jump: channel => { asked.push(channel); return Promise.resolve(""); }}}},
  };
  vm.createContext(context);
  vm.runInContext(source("jumpTo"), context);

  vm.runInContext("jumpTo({channel: 'claude:gone', jump_problem: 'Recorded tmux pane is gone or ambiguous; no jump made'})", context);
  assert.deepEqual(asked, ["claude:gone"]);
});

test("a jump that works goes back to the whole grove; one that fails stays to say why", async () => {
  const msg = {}, whole = [];
  const context = {
    hideCard: () => {}, wholeGrove: () => whole.push(true), draw: () => {}, document: {getElementById: () => msg},
    window: {pywebview: {api: {jump: channel => Promise.resolve(channel === "claude:here" ? "" : "Can't jump")}}},
  };
  vm.createContext(context);
  vm.runInContext(source("jumpTo"), context);

  vm.runInContext("jumpTo({channel: 'claude:here'})", context);
  await new Promise(setImmediate);
  assert.equal(whole.length, 1);
  vm.runInContext("jumpTo({channel: 'claude:gone'})", context);
  await new Promise(setImmediate);
  assert.equal(whole.length, 1);
  assert.equal(msg.textContent, "Can't jump");
});

function listing() {
  const painted = [];
  const context = {
    CW: 8, RH: 16, BG: "#0d1117", TEXT: "#e6ebf2", STATUS: {done: "#6f9fe0"}, ASKS: [], flipped: false, listMarks: [],
    ctx: {fillRect: () => {}}, listHeight: () => 52, listPad: () => 2, mix: a => a, frame: () => {}, drawTag: () => {},
    shownKey, txt: (text, _x, _y, color) => painted.push([text, color]),
  };
  vm.createContext(context);
  vm.runInContext(source("drawList"), context);
  return {draw: (t, w = 480) => context.drawList({color: ""}, t, 0, 0, w, {key: ` ${t.letter} `, body: ""}), painted};
}

test("each lemon's key in a tree's list takes its status's color, as the terminal grove's does", () => {
  const {draw, painted} = listing();
  const lemons = [{status: "", age: "8m", name: "browser grove"}, {status: "done", age: "22h", name: "Review"}];

  draw({key: "grove/richer-rendering", letter: "r", lemons});
  const color = key => painted.find(([text]) => text === key)[1];
  assert.equal(color(".r1"), "#6f9fe0");
  assert.equal(color("r"), "#c9d1d9");
});

test("a list names its tree's key, unless it is its chat lemon's channel", () => {
  const room = "openclaw:agent:main:matrix:channel:!r00mA1b2:grove.example";
  const {draw, painted} = listing();

  draw({key: "grove/richer-rendering", letter: "r", lemons: [{status: "", age: "8m", name: "browser grove"}]});
  draw({key: room, letter: "g", lemons: [{status: "", age: "8m", name: "garden", channel: room}]}, 4000);
  const texts = painted.map(([text]) => text.trim());
  assert.ok(texts.includes("grove/richer-rendering"));
  assert.ok(!texts.some(text => text.includes("openclaw:")));
});

test("esc and backspace back out of a block, then go back to the terminal rather than closing", () => {
  const asked = [];
  const context = {
    zoomed: "3", goTo: d => { context.zoomed = d; }, draw: () => {},
    window: {pywebview: {api: {to_terminal: () => asked.push("terminal"), dismiss: () => asked.push("dismiss")}}},
  };
  vm.createContext(context);
  vm.runInContext(source("back"), context);

  context.back();
  assert.deepEqual(asked, []);
  context.back();
  assert.deepEqual(asked, ["terminal"]);
});

test("a lemon hanging in a crown is a tap target of its own on a touch screen only", () => {
  const lemon = {channel: "claude:a"}, tree = {key: "t", lemons: [lemon]}, box = {fruit: [{x: 1, y: 2, w: 12, h: 12, lemon}]};
  for (const web of [true, false]) {  // a touch screen, then a mouse
    const context = {window: {matchMedia: () => ({matches: web})}, hits: []};
    vm.createContext(context);
    vm.runInContext('const touch = () => window.matchMedia?.("(pointer: coarse)").matches;\n' + source("fruitHits"), context);
    context.fruitHits({digit: "1"}, box, () => tree);
    assert.deepEqual(context.hits.map(h => [h.lemon, h.tree]), web ? [[lemon, tree]] : []);
  }
});

for (const many of [12, 20]) test(`each of ${many} lemons in a tree opened on a short touch screen has its own row on the screen to tap`, () => {
  const lemons = Array.from({length: many}, (_, i) => ({channel: `claude:${i}`, name: `lemon ${i}`, status: "merge"}));
  const tree = {key: "t", label: "mops", letter: "t", lemons};
  const context = {
    W: () => 500, H: () => 269, RH: 18, CW: 9, BG: "#000", TEXT: "#fff", TAG: "#333", STATUS: {}, ASKS: ["merge"],
    view: {treeZ: 1}, hits: [], focus: {digit: "6", key: "t"},
    ctx: {fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}},
    focused: () => ({b: {digit: "6", group: many === 20 ? "mops" : ""}, t: tree, each: () => tree}),
    crownExtent: () => ({left: -4, right: 4, top: -6, bottom: 0}), crownShape: () => ({}),
    drawTree: (b, t, cx, cy) => ({groundY: cy + 18 * context.view.treeZ, fruit: []}),
    fruitHits: () => {}, txtAt: () => {}, mix: c => c,
  };
  vm.createContext(context);
  vm.runInContext(source("drawFocus"), context);
  assert.equal(context.drawFocus(), true);
  const rows = context.hits.filter(h => h.lemon);
  assert.equal(rows.length, many);
  assert.equal(context.hits.filter(h => h.blockMenu).length, many === 20 ? 1 : 0);  // a group's title opens its block's menu
  assert.ok(rows.every(h => h.y >= 0 && h.y + h.h <= 269 && h.x >= 0 && h.x + h.w <= 500), rows.map(h => [h.x, h.y, h.y + h.h]).join(" "));
  const overlaps = (a, b) => a.x + 0.01 < b.x + b.w && b.x + 0.01 < a.x + a.w && a.y + 0.01 < b.y + b.h && b.y + 0.01 < a.y + a.h;  // rows meet edge to edge
  assert.ok(rows.every((a, i) => rows.every((b, j) => i === j || !overlaps(a, b))));
});

test("the browser's back button closes an open tree, then the block, and the page leaves no entry behind", () => {
  const listeners = {}, stack = [null];
  const history = {
    get state() { return stack[stack.length - 1]; },
    pushState: s => stack.push(s),
    back: () => { stack.pop(); listeners.popstate(); },
  };
  const context = {history, window: {addEventListener: (n, f) => { listeners[n] = f; }}, zoomed: null, focus: null};
  context.goTo = d => { context.zoomed = d; };
  vm.createContext(context);
  vm.runInContext(page.match(/let leaving = false;[^]*?\n\}\);/)[0] + "\nfunction draw() { inHistory(); }", context);
  const at = () => [vm.runInContext("zoomed", context), Boolean(vm.runInContext("focus", context)), stack.length];

  vm.runInContext('zoomed = "6"; draw(); focus = {digit: "6", key: "t"}; draw()', context);
  assert.deepEqual(at(), ["6", true, 2]);
  history.back();
  assert.deepEqual(at(), ["6", false, 2]);
  history.back();
  assert.deepEqual(at(), [null, false, 1]);
  vm.runInContext('zoomed = "6"; draw(); zoomed = null; draw()', context);  // a tap back out to the whole grove
  assert.deepEqual(at(), [null, false, 1]);
});
