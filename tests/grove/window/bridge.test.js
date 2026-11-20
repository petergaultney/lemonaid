// The bridge where a road crosses the stream (`paintBridges` in src/lemonaid/grove/window/static/page.html),
// run by `node --test` against the page's own functions on a grid that records what it paints.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const page = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/window/static/page.html"), "utf8");
const source = name => page.match(new RegExp(`function ${name}\\([^]*?\\n\\}`))[0];

// The cells a bridge paints for *road* over *stream* (grove units), three cells a column, rows twice as tall.
function bridged(road, stream) {
  const painted = new Set(), grid = {per: 3, i0: 0, j0: 0, paint: (i, j) => painted.add(`${i},${j}`)};
  const page = {YS: 2};
  vm.createContext(page);
  vm.runInContext(`${source("smooth")}\n${source("paintBridges")}`, page);
  page.paintBridges(grid, [road], stream);
  return painted;
}
// Whether the cell on the road's middle, *along* cells from where it meets the stream at (*x*, *y*), is painted.
const onRoad = (painted, [x, y], [tx, ty], along) => painted.has(`${Math.floor(x + tx * along)},${Math.floor(y + ty * along)}`);

test("a bridge across the stream reaches past both banks", () => {
  const painted = bridged([[50, 30], [50, 60]], [[0, 45], [100, 45]]);
  const at = [150, 270], down = [0, 1];  // in cells: x three to a column, y six to a row

  for (const along of [-6, 6]) assert.ok(onRoad(painted, at, down, along), `no bridge ${along} cells from the middle`);
  assert.ok(!onRoad(painted, at, down, 14), "the bridge runs on past the banks");
});

test("a bridge slanting shallowly over the stream still reaches past both banks", () => {
  const painted = bridged([[0, 40], [100, 50]], [[0, 45], [100, 45]]);
  const l = Math.hypot(300, 60), along = [300 / l, 60 / l], at = [150, 270];  // the road in cells crosses at its middle

  for (const reach of [-26, 26]) assert.ok(onRoad(painted, at, along, reach), `no bridge ${reach} cells along the road`);
});

test("a road all but alongside the stream is bridged for as long as it's over the water", () => {
  const painted = bridged([[0, 44], [100, 46]], [[0, 45], [100, 45]]);
  const l = Math.hypot(300, 12), along = [300 / l, 12 / l], at = [150, 270];

  for (const reach of [-80, 80]) assert.ok(onRoad(painted, at, along, reach), `no bridge ${reach} cells along the road`);
});

test("a road beside the stream that never crosses it has no bridge", () => {
  assert.equal(bridged([[0, 43], [100, 43]], [[0, 45], [100, 45]]).size, 0);
});
