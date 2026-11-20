// Where the grove window puts each tree's tag (the grove view) or lemon list (a block's view).
// Pure functions of the grove's data and the screen's measures, so node can test them; the page
// inlines this file ahead of its own script.

function noise(a, b) {
  let h = (Math.imul(a, 374761393) + Math.imul(b, 668265263)) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function wordHash(w) { let h = 7; for (const c of w) h = (Math.imul(h, 31) + c.codePointAt(0)) & 0x7fffffff; return h; }

// A crown as lit leaf clumps (clumps.crown), in cell units: x in columns, y in rows.
function crownShape(t, size) {
  const n = Math.min(t.lemons.length, 5), seed = wordHash(t.key), lead = t.lead, j = k => noise(seed, k) - 0.5;
  const ry = 0.85 * Math.max(1.35, 0.5 * n + 0.6, Math.min((1.2 + n * 0.15 + (lead ? 0.4 : 0)) * size, 4));
  const rx = Math.min(Math.max(2.6, (3.6 + n * 1.0 + (lead ? 1.4 : 0)) * size, 2.6 * Math.min(ry, 2.6)), 3.1 * ry);
  const cy = -0.25 * ry, tall = 2 * 1.1 * ry, sz = 0.62 * Math.min(0.5 * Math.min(rx, tall), 4.8);
  const count = Math.max(3, Math.round(1.8 * rx / sz));
  const clump = (x, y, scale) => {
    const r = sz * scale, shine = j(5000 + 37 * Math.round(4 * x / rx) + Math.round(8 * y / tall));
    let lit = 0.5 - 0.45 * x / rx - 0.6 * y / tall - 0.7 * Math.max(0, y / tall + 0.1);
    return [x, cy + y / 2, r, r / 2, Math.min(1, Math.max(0, lit + 0.4 * shine))];
  };
  const ring = [...Array(count).keys()].map(i => {
    const a = (175 + 190 * (i + 0.5 + 0.4 * j(3 * i)) / count) * Math.PI / 180, scale = 0.95 + 0.35 * j(3 * i + 1), r = sz * scale;
    return clump((rx - r) * Math.cos(a), (tall - r) * Math.sin(a), scale);
  });
  const middle = [...Array(rx < 5 ? 1 : 2).keys()].map(i => clump(0.5 * rx * j(40 + 2 * i), tall * (0.3 * j(41 + 2 * i) - 0.1), 0.8));
  // One wide, shallow clump underneath instead of an arc of them, which read as two lobes.
  const under = [[0.08 * rx * j(50), cy + 0.3 * tall, 0.82 * rx, 0.22 * tall, 0.15]];
  const behind = [0, cy - 0.05 * tall, 0.88 * rx, 0.62 * tall / 2, 0.45];
  return {rx, ry, blobs: [behind, ...[...ring, ...middle, ...under].sort((a, b) => a[1] - b[1])], bark: rx < 7 ? 2 : rx < 13 ? 4 : 6};
}
function crownExtent(s) {
  return {
    top: Math.min(...s.blobs.map(bl => bl[1] - bl[3])), bottom: Math.max(...s.blobs.map(bl => bl[1] + bl[3])),
    left: Math.min(...s.blobs.map(bl => bl[0] - bl[2])), right: Math.max(...s.blobs.map(bl => bl[0] + bl[2])),
  };
}
// A tree's whole box (a lead's crown above it included), its crown alone, and the ground its trunk
// stands on, in screen pixels for a cell *cw* by *rh*.
function treeBox(t, s, cx, cy, cw, rh) {
  const {top, bottom, left, right} = crownExtent(s), groundY = cy + (bottom + 0.55) * rh, crown = t.lead ? rh * 1.6 : 0;
  return {x: cx + left * cw, y: cy + top * rh - crown, w: (right - left) * cw, h: groundY - (cy + top * rh) + crown, groundY,
    crown: {x: cx + left * cw, y: cy + top * rh, w: (right - left) * cw, h: (bottom - top) * rh * 0.9}};
}
// A tree's size comes from its lemons alone (`crownShape`), never from where it stands: the layout's
// `size`, which shrinks a crowded tree to fit terminal cells, is the terminal grove's.
const treeScale = (_t, zoomed) => (zoomed ? 1.25 : 1);

function tagParts(b, t, zoomed, full, most) {
  const key = ` ${zoomed ? "" : b.digit}${t.letter} `, head = (t.lead ? "♛ " : "") + (t.lemons[0]?.emoji ? t.lemons[0].emoji + " " : "");
  const max = full ? 60 : most || 22, label = t.label.length > max ? t.label.slice(0, max - 1) + "…" : t.label;
  return {key, body: ` ${head}${label} `};
}
const listPad = rh => Math.round(rh * 0.3);  // room inside a list's border above and below its rows
// Its fill reaches as far past the border below as at the sides, half a column (about a quarter row).
const listHeight = (t, rh) => (t.lemons.length + 1) * rh + 2 * listPad(rh) + Math.round(rh / 4);
// As wide as its title or its longest row needs, up to *most*: a narrow list covers less of its block.
function listWidth(t, parts, most, cw) {  // in unscaled label pixels
  const title = parts.key.length + parts.body.length + t.key.length + 4;
  const rows = Math.max(...t.lemons.map(l => (l.name || l.session).length)) + 36;
  return Math.min(Math.floor(most / cw), Math.max(title, rows)) * cw;  // whole columns, so its right side matches its left
}

function placer() {
  const boxes = [];
  const hitsAny = r => boxes.some(o => r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h);
  return {
    reserve: r => boxes.push(r),
    place: (cands, within) => {  // a spot inside *within* (the block) first, then any
      const inBlock = c => !within || (c.x >= within.x && c.x + c.w <= within.x + within.w && c.y >= within.y && c.y + c.h <= within.y + within.h);
      const r = cands.find(c => inBlock(c) && !hitsAny(c)) || cands.find(c => !hitsAny(c));
      if (r) boxes.push(r);
      return r;
    },
  };
}

// The view (a corner in grove units and pixels per column, *k*) that fits a grove rectangle on screen.
function fitView(x, y, w, h, pad, screen) {
  const k = Math.min(screen.W / (w + 2 * pad), screen.H / ((h + 2 * pad) * screen.YS));
  return {k, x: x + w / 2 - screen.W / 2 / k, y: y + h / 2 - screen.H / 2 / (k * screen.YS)};
}
function groveView(blocks, screen) {
  const ps = blocks.map(b => b.plot), x0 = Math.min(...ps.map(p => p.x)), y0 = Math.min(...ps.map(p => p.y));
  return fitView(x0, y0, Math.max(...ps.map(p => p.x + p.w)) - x0, Math.max(...ps.map(p => p.y + p.h)) - y0, 1, screen);
}
// A view kept in a window *then* ({W, H}) brought to one sized *now*: the same middle of the map, zoomed
// as far past the view's fit at the new size (*fitNow*) as it was past its fit then (*fitThen*).
function carriedView(kept, then, now, fitThen, fitNow, YS) {
  const cx = kept.x + then.W / 2 / kept.k, cy = kept.y + then.H / 2 / (kept.k * YS), k = kept.k * fitNow.k / fitThen.k;
  return {k, x: cx - now.W / 2 / k, y: cy - now.H / 2 / (k * YS)};
}
// A view's own fit: the whole grove, or the zoomed block.
function homeView(blocks, zoomed, screen) {
  if (!zoomed) return groveView(blocks, screen);

  const p = blocks.find(b => b.digit === zoomed).plot;
  return fitView(p.x, p.y, p.w, p.h, 2, screen);
}

// Each tree's tag or list, keyed `digit/key`, worked out at the view's own fit (`k0`) and kept in grove
// units (`wx`, `wy`; `w` and `h` stay pixels at `k0`), so panning and zooming move labels with the map
// and never re-place them. *ls* is the label size, against the map's own text.
function layOut(blocks, zoomed, screen, ls) {
  const {CW, RH, YS} = screen, view = homeView(blocks, zoomed, screen), cw = 0.75 * view.k, rh = cw * RH / CW;
  const sx = x => (x - view.x) * view.k, sy = y => (y - view.y) * view.k * YS;
  const lcw = CW * ls, lrh = RH * ls;
  const P = placer(), out = new Map(), world = r => ({wx: view.x + r.x / view.k, wy: view.y + r.y / (view.k * YS), w: r.w, h: r.h});
  const trees = [];
  blocks.forEach(b => {
    const p = b.plot, rect = {x: sx(p.x), y: sy(p.y), w: p.w * view.k, h: p.h * view.k * YS};
    if (!b.group) { P.reserve({x: rect.x - CW, y: rect.y - RH, w: rect.w + 2 * CW, h: rect.h + RH}); return; }
    P.reserve({x: rect.x + Math.min(4 * CW, rect.w / 8), y: rect.y - RH * 0.6, w: (b.group.length + 4) * CW, h: RH});
    if (zoomed && zoomed !== b.digit) return;
    b.trees.forEach(t => {
      const cx = sx(p.x + t.spot[0]), box = treeBox(t, crownShape(t, treeScale(t, zoomed)), cx, sy(p.y + t.spot[1]), cw, rh);
      P.reserve(box.crown); trees.push({b, t, cx, box, rect});  // only a crown blocks a label, not its trunk
    });
  });
  const lw = Math.max(54, Math.min(72, Math.floor(screen.W * 0.3 / CW))) * lcw;
  const inBlock = (x, w, rect) => Math.max(rect.x + lcw / 2, Math.min(rect.x + rect.w - w - lcw / 2, x));
  // A fixed order, by block and letter, so a status changing never changes who gets which spot.
  trees.sort((a, c) => a.b.digit.localeCompare(c.b.digit) || a.t.letter.localeCompare(c.t.letter));
  trees.forEach(({b, t, cx, box, rect}) => {
    const id = `${b.digit}/${t.key}`;
    if (zoomed) {  // a list always hangs below its tree, its tag (the title) centered under the trunk
      const parts = tagParts(b, t, zoomed, true), tw = (parts.key.length + parts.body.length) * lcw, w = listWidth(t, parts, lw / ls, CW) * ls;
      out.set(id, {kind: "list", parts, ...world({x: inBlock(cx - tw / 2 - lcw, w, rect), y: box.groundY, w, h: listHeight(t, RH) * ls})});
      return;
    }
    // As the terminal grove fits a tag (draw/tag_fit.py): its whole name first, then four characters
    // shorter at a time; anywhere on its block that keeps the trunk under it, nearest centered first;
    // on its row under the crown, then one row lower.
    const spots = (tw, y) => {
      const lo = Math.max(cx - tw + lcw, rect.x + lcw / 2), hi = Math.min(cx - lcw, rect.x + rect.w - tw - lcw / 2);
      const xs = [];
      for (let x = lo; x <= hi; x += lcw) xs.push(x);
      return xs.sort((a, c) => Math.abs(a - (cx - tw / 2)) - Math.abs(c - (cx - tw / 2))).map(x => ({x, y, w: tw, h: lrh}));
    };
    const whole = t.label.length;
    for (const max of [...new Set([whole, ...Array.from({length: Math.ceil(whole / 4)}, (_, i) => whole - 4 * (i + 1))])].filter(n => n > 0 && (n >= 4 || n === whole))) {
      const parts = tagParts(b, t, zoomed, false, max), tw = (parts.key.length + parts.body.length) * lcw;
      const at = P.place([...spots(tw, box.groundY), ...spots(tw, box.groundY + lrh)]);
      if (at) { out.set(id, {kind: "tag", parts, ...world(at)}); return; }
    }
    const parts = {key: ` ${b.digit}${t.letter} `, body: ""}, tw = parts.key.length * lcw;
    const at = P.place([...spots(tw, box.groundY), ...spots(tw, box.groundY + lrh)]) || {x: cx - tw / 2, y: box.groundY, w: tw, h: lrh};
    out.set(id, {kind: "tag", parts, ...world(at)});
  });
  out.ls = ls;
  out.k0 = view.k;
  return out;
}

if (typeof module !== "undefined") module.exports = {carriedView, crownShape, homeView, layOut, treeBox, treeScale};
