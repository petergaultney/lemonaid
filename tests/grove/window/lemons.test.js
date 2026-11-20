// Where a tree's lemons hang (`lemonSpots` in src/lemonaid/grove/window/static/page.html), run by
// `node --test` against the page's own function.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const here = path.join(__dirname, "../../../src/lemonaid/grove/window/static");
const page = fs.readFileSync(path.join(here, "page.html"), "utf8");
const source = name => page.match(new RegExp(`function ${name}\\([^]*?\\n\\}`))[0];
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(`${fs.readFileSync(path.join(here, "layout.js"), "utf8")}\n${source("lemonSpots")}\nthis.lemonSpots = lemonSpots; this.wordHash = wordHash;`, sandbox);
const spotsOf = (key, n) => sandbox.lemonSpots(sandbox.wordHash(key), n);
const keys = [...Array(500).keys()].map(k => `grove.${k}`);

test("a tree gaining lemons leaves the others where they are", () => {
  for (const key of keys.slice(0, 50)) assert.deepEqual(spotsOf(key, 6).slice(0, 2), spotsOf(key, 2));
});

test("two lemons on a tree hang well apart, one above the other, never level like a pair of eyes", () => {
  for (const key of keys) {
    const [[u, v], [a, b]] = spotsOf(key, 2);

    assert.ok(Math.abs(v - b) >= 1, `${key}: lemons at ${v.toFixed(2)} and ${b.toFixed(2)} down`);
    assert.ok(Math.hypot(u - a, 0.5 * (v - b)) >= 0.5, `${key}: lemons huddle`);
  }
});

test("two-lemon trees don't all hang theirs the same way", () => {
  const ways = new Set(keys.map(key => {
    const [[u, v], [a, b]] = spotsOf(key, 2);
    return `${Math.sign(a - u)} ${Math.sign(b - v)}`;
  }));

  assert.equal(ways.size, 4);
});

test("every lemon keeps clear of the others, however many hang on a tree", () => {
  for (const key of keys) {
    const spots = spotsOf(key, 6);
    spots.forEach(([u, v], i) => spots.slice(0, i).forEach(([a, b]) => assert.ok(Math.hypot(u - a, 0.5 * (v - b)) >= 0.3, `${key}: lemon ${i} huddles`)));
  }
});

test("no lemon hangs low in the middle of its crown, sitting on the trunk", () => {
  for (const key of keys) for (const [u, v] of spotsOf(key, 6)) assert.ok(v < 0.3 || Math.abs(u) > 0.5, `${key}: a lemon at ${u.toFixed(2)} across, ${v.toFixed(2)} down`);
});
