// A tree drag over its cached frame (`drawDrag` in src/lemonaid/grove/window/static/page.html), run by
// `node --test` against the page's own functions with a recording stand-in for the canvas.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const page = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/page.html"), "utf8");
const source = name => page.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\}`))[0];

function dragging() {
  const page = {drawn: null};
  const noop = () => {};
  Object.assign(page, {
    ctx: new Proxy({drawImage: from => { page.drawn = from.position; }}, {get: (o, k) => o[k] || noop}),
    cv: {width: 100, height: 100}, dragBase: {position: "frame without the tree"}, still: {position: 1},
    DATA: {}, shown: true, zoomed: "1", hits: [{}], drag: {b: {plot: {x: 0, y: 0}}, t: {spot: [0, 0]}, fx: 2, fy: 0, problem: ""},
    pulsers: {dots: [{x: 0, y: 0, r: 1, base: "#111111"}], tags: [{}]},
    drawTree: (_b, _t, x) => { page.drawn = x; return {x, y: 0, w: 1, groundY: 1}; },
    drawLabel: () => { page.hits.push({}); page.pulsers.tags.push({}); },
    treeScale: () => 1, sx: x => x, sy: y => y, phase: () => 0, mix: () => "#111111", BG: "#000000", PULSE_DEPTH: 0.45,
  });
  vm.createContext(page);
  vm.runInContext(`${source("drawDrag")}\n${source("pulse")}\n${source("frame")}`, page);
  return page;
}

test("a pulse during a drag leaves the tree where the pointer has it", () => {
  const page = dragging();

  vm.runInContext("drawDrag()", page);
  assert.equal(page.drawn, 2);
  vm.runInContext("pulse()", page);
  assert.equal(page.drawn, 2, "a pulse painted the frame from before the drag over it");
});

test("a drag's overlay adds nothing to what the frame can be clicked or pulsed at", () => {
  const page = dragging();

  vm.runInContext("drawDrag(); drawDrag()", page);
  assert.equal(page.hits.length, 1);
  assert.equal(page.pulsers.tags.length, 1);
});

test("a refresh before the save answers keeps the same landing, so the answer can still end it", () => {
  const page = {moving: null};
  vm.createContext(page);
  vm.runInContext(source("landed"), page);
  const old = {digit: "1", trees: [{key: "ant", spot: [3, 3]}]};
  page.drag = {b: old, t: old.trees[0], x: 9, y: 3, landing: true};
  const landing = page.drag;

  vm.runInContext("landed(d)", Object.assign(page, {d: {blocks: [{digit: "1", trees: [{key: "ant", spot: [3, 3]}]}]}}));
  assert.equal(page.drag, landing, "the refresh replaced the landing");
  assert.notEqual(page.drag.t, old.trees[0], "the landing kept the old tree object");
  vm.runInContext("landed(d)", Object.assign(page, {d: {blocks: [{digit: "1", trees: [{key: "ant", spot: [9, 3]}]}]}}));
  assert.equal(page.drag, null);
});

test("a list's other page keeps PRs and branch clear of the model, however long", () => {
  const runs = [];
  const page = {CW: 8, TEXT: "#fff", BRANCH: "#d16ad8", txt: (s, x) => runs.push({s, x, end: x + s.length * 8})};
  vm.createContext(page);
  vm.runInContext(source("otherPage"), page);
  const right = 60 * 8, model = right - 16 * 8;
  const lemon = {prs: [["6541", ""], ["6700", ""], ["6721", ""]], branch: "a/" + "b".repeat(80), model: "Sonnet 5.5", context: "42%", age: "4m ago"};

  vm.runInContext("otherPage(lemon, 7 * 8, right, 0)", Object.assign(page, {lemon, right}));
  const before = runs.filter(r => r.x < model);
  assert.ok(before.length >= 2, "nothing drawn before the model column");
  for (const r of before) assert.ok(r.end <= model - 8, `${r.s} runs to ${r.end}, into the model at ${model}`);
  assert.ok(runs.some(r => r.x === model && r.s === "Sonnet 5.5"));
  assert.ok(runs.some(r => r.s === "4m" && r.end === right), "the age is not drawn at the right edge");
  assert.ok(!runs.some(r => r.s === "42%"), "the context is drawn on the other page");
});

function usage() {
  const replies = [];
  const box = {style: {display: "none"}, innerHTML: ""};
  const page = {
    usageAsked: 0, usageTimer: 0, timers: 0, setTimeout: () => ++page.timers, clearTimeout: () => {},
    document: {getElementById: () => box},
    window: {pywebview: {api: {usage: () => new Promise(resolve => replies.push(resolve))}}},
  };
  vm.createContext(page);
  vm.runInContext(`const usageOpen = () => document.getElementById("usage").style.display === "block";\n${source("showUsage")}\n${source("hideUsage")}`, page);
  return {page, box, replies};
}

test("a usage reply that comes after the box was dismissed leaves it closed", async () => {
  const {page, box, replies} = usage();

  const first = vm.runInContext("showUsage()", page);
  vm.runInContext("hideUsage()", page);
  replies[0]([]);
  await first;
  assert.equal(box.style.display, "none", "the first answer reopened a dismissed box");

  const opened = vm.runInContext("showUsage()", page);
  replies[1]([]);
  await opened;
  assert.equal(box.style.display, "block");
  const timers = page.timers;
  const refresh = vm.runInContext("showUsage()", page);  // the 30-second refresh
  vm.runInContext("hideUsage()", page);
  replies[2]([]);
  await refresh;
  assert.equal(box.style.display, "none", "a refresh's answer reopened a dismissed box");
  assert.equal(page.timers, timers, "a refresh's answer restarted the timer after dismissal");
});
