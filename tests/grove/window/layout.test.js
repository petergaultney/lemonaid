// The grove window's label layout (src/lemonaid/grove/window/static/layout.js), run by `node --test`.
const test = require("node:test");
const assert = require("node:assert/strict");
const {carriedView, crownShape, homeView, layOut, treeBox, treeScale} = require("../../../src/lemonaid/grove/window/static/layout.js");

const SCREEN = {W: 1600, H: 900, CW: 8, RH: 16, YS: 2};
const lemon = (status, name) => ({status, name, session: name, age: "3m ago", working: false});
const tree = (letter, key, spot, label = `${key} work`) => ({letter, key, label, spot, lead: false, size: 1, lemons: [lemon("", key)]});

function grove() {
  return [
    {digit: "1", group: "roomy", plot: {x: 2, y: 2, w: 60, h: 14},
      trees: [tree("a", "ant", [10, 6]), tree("b", "bee", [30, 6]), tree("c", "cat", [44, 4]), tree("d", "elk", [57, 10], "close to the edge")]},
    {digit: "2", group: "crowded", plot: {x: 66, y: 2, w: 30, h: 14},
      trees: [tree("a", "dog", [8, 6], "a much longer label than fits"), tree("b", "eel", [11, 6], "another long label here"), tree("c", "fox", [20, 6])]},
    {digit: "3", group: "", plot: {x: 2, y: 20, w: 20, h: 6}, trees: [{...tree("a", "gnu", [0, 0]), bay: 0}]},
  ];
}

// A label's box, and its tree's ground and block, in pixels at the view's own fit.
function placed(blocks, zoomed, ls = 0.72) {
  const out = layOut(blocks, zoomed, SCREEN, ls), v = homeView(blocks, zoomed, SCREEN), k = out.k0, cw = 0.75 * k;
  const sx = x => (x - v.x) * k, sy = y => (y - v.y) * k * SCREEN.YS;
  return [...out].map(([id, at]) => {
    const b = blocks.find(b => b.digit === id.split("/")[0]), t = b.trees.find(t => `${b.digit}/${t.key}` === id);
    const cx = sx(b.plot.x + t.spot[0]), box = treeBox(t, crownShape(t, treeScale(t, zoomed)), cx, sy(b.plot.y + t.spot[1]), cw, cw * SCREEN.RH / SCREEN.CW);
    return {id, kind: at.kind, x: sx(at.wx), y: sy(at.wy), w: at.w, h: at.h, groundY: box.groundY, cx,
      block: {x: sx(b.plot.x), w: b.plot.w * k}};
  });
}
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

test("every grove tree gets a tag below its tree, and the packhouse's trees none", () => {
  const labels = placed(grove(), null);

  assert.deepEqual(labels.map(l => l.id).sort(), ["1/ant", "1/bee", "1/cat", "1/elk", "2/dog", "2/eel", "2/fox"]);
  for (const l of labels) {
    assert.equal(l.kind, "tag");
    assert.ok(l.y >= l.groundY - 1e-6, `${l.id} sits above its tree's ground`);
  }
});

test("a tree with room has its tag centered under its trunk", () => {
  for (const l of placed(grove(), null).filter(l => ["1/ant", "1/bee"].includes(l.id))) {
    assert.ok(Math.abs(l.x + l.w / 2 - l.cx) < 1, `${l.id} is off center`);
  }
});

test("tags stay on their blocks and clear of each other where trees crowd", () => {
  const labels = placed(grove(), null);

  for (const l of labels) assert.ok(l.x >= l.block.x && l.x + l.w <= l.block.x + l.block.w, `${l.id} spills off its block`);
  labels.forEach((a, i) => labels.slice(i + 1).forEach(b => assert.ok(!overlap(a, b), `${a.id} overlaps ${b.id}`)));
});

test("a status change, a refresh's new objects or a new order places no label differently", () => {
  const before = layOut(grove(), null, SCREEN, 0.72);
  const changed = grove().reverse();
  changed.forEach(b => { b.trees.reverse(); b.trees.forEach(t => t.lemons.forEach(l => { l.status = "blocked"; l.working = true; })); });

  assert.deepEqual(layOut(changed, null, SCREEN, 0.72), before);
});

test("a block's view hangs a list under each of its trees and labels no other block", () => {
  const labels = placed(grove(), "1", 0.88);

  assert.deepEqual(labels.map(l => l.id).sort(), ["1/ant", "1/bee", "1/cat", "1/elk"]);
  for (const l of labels) {
    assert.equal(l.kind, "list");
    assert.ok(l.y >= l.groundY - 1e-6, `${l.id} sits above its tree's ground`);
    assert.ok(l.x >= l.block.x && l.x + l.w <= l.block.x + l.block.w, `${l.id} spills off its block`);
  }
});

test("a smaller label size gives smaller tags", () => {
  const small = placed(grove(), null, 0.5), big = placed(grove(), null, 0.9);

  small.forEach((l, i) => assert.ok(l.w < big[i].w, `${l.id} didn't shrink`));
});

test("a tree's size follows its lemons, not where it stands or how crowded it is", () => {
  const two = (size, spot) => ({...tree("a", "ant", spot), size, lemons: [lemon("", "x"), lemon("", "y")]});
  const crown = (t, zoomed) => treeBox(t, crownShape(t, treeScale(t, zoomed)), 0, 0, 10, 20).crown;

  assert.deepEqual(crown(two(0.6, [5, 5]), null), crown(two(1.4, [40, 9]), null));
  assert.deepEqual(crown(two(0.6, [5, 5]), "1"), crown(two(1.4, [40, 9]), "1"));
  const one = {...two(1, [5, 5]), lemons: [lemon("", "x")]};
  assert.ok(crown(two(1, [5, 5]), null).w > crown(one, null).w, "a tree with more lemons is no bigger");
});

test("a tag with room shows its whole name, however long", () => {
  const long = "a name much longer than twenty-two characters";
  const blocks = [{digit: "1", group: "wide", plot: {x: 2, y: 2, w: 100, h: 14}, trees: [tree("a", "ant", [50, 6], long)]}];
  const [, at] = [...layOut(blocks, null, SCREEN, 0.72)][0];

  assert.ok(at.parts.body.includes(long), at.parts.body);
});

test("a view carried to a window of another size keeps its middle and how far past the fit it zoomed", () => {
  const then = {W: 1000, H: 600}, now = {W: 2000, H: 1200}, YS = 2;
  const kept = {x: 10, y: 5, k: 8};
  const carried = carriedView(kept, then, now, {k: 4}, {k: 8}, YS);

  assert.equal(carried.k, 16);
  const middle = (v, s) => [v.x + s.W / 2 / v.k, v.y + s.H / 2 / (v.k * YS)];
  assert.deepEqual(middle(carried, now), middle(kept, then));
});
