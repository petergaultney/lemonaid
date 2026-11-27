// A message's attachments (src/lemonaid/grove/web/attach.js), run by `node --test` with stand-ins
// for the page's elements, its storage and the server's attach and detach calls.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/attach.js"), "utf8");

class Element {
  constructor() { this.children = []; this.hidden = false; this.textContent = ""; this.listeners = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
}

// A page whose storage starts as *stored*; the server answers each upload with the next id.
function page(stored = {}) {
  const store = {...stored}, calls = [];
  let next = 0, hold = null, decode = null;
  const context = {
    localStorage: {
      getItem: key => store[key] ?? null,
      setItem: (key, value) => { store[key] = value; },
      removeItem: key => { delete store[key]; },
    },
    document: {createElement: () => new Element()},
    btoa: s => Buffer.from(s, "binary").toString("base64"),
    createImageBitmap: () => new Promise(r => { decode = r; }),
    fetch: async (url, request) => {
      const args = JSON.parse(request.body);
      calls.push([url, args]);
      if (hold) await hold;
      const answer = url === "api/attach" ? {id: `id${next++}`, name: args[0], size: 2, mime: args[1]} : "";
      return {ok: true, json: async () => answer};
    },
  };
  context.window = context;
  vm.runInNewContext(script, context);
  const said = [], list = new Element();
  return {
    store, calls, list, said,
    attach: channel => context.window.groveAttach(channel, list, line => said.push(line)),
    finishDecoding: () => decode && decode({width: 10, height: 10}),
    holdUploads: () => { let release; hold = new Promise(r => { release = r; }); return () => { hold = null; release(); }; },
  };
}

const file = (name, text = "hi", type = "text/plain") => ({
  name, type, size: text.length, arrayBuffer: async () => new TextEncoder().encode(text).buffer,
});
const plain = x => JSON.parse(JSON.stringify(x));  // out of the page's context, to compare
// Each tile's file name, and a tile's part by its class.
const part = (tile, cls) => {
  for (const child of tile.children) {
    if (child.className === cls) return child;
    const inner = child.children && part(child, cls);
    if (inner) return inner;
  }
  return null;
};
const names = list => list.children.map(tile => part(tile, "name").textContent);

test("a picked file uploads and stays in the draft when the page is drawn again", async () => {
  const first = page();
  await first.attach("claude:a").add([file("notes.txt")]);

  assert.deepEqual(first.calls, [["api/attach", ["notes.txt", "text/plain", "aGk="]]]);
  const again = page(first.store).attach("claude:a");
  assert.deepEqual(plain(again.ids()), ["id0"]);
  assert.deepEqual(plain(again.files()), [{name: "notes.txt", size: 2, thumb: ""}]);
});

test("each lemon keeps its own attachments", async () => {
  const shown = page();
  await shown.attach("claude:a").add([file("a.txt")]);

  assert.deepEqual(plain(page(shown.store).attach("claude:b").ids()), []);
});

test("a removed attachment leaves the draft and the server", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  await attached.add([file("a.txt"), file("b.txt")]);

  part(shown.list.children[0], "remove").listeners.click();

  assert.deepEqual(plain(attached.ids()), ["id1"]);
  assert.deepEqual(names(shown.list), ["b.txt"]);
  assert.deepEqual(shown.calls.at(-1), ["api/detach", ["id0"]]);
});

test("a sent message's files leave the draft but stay on the server", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  await attached.add([file("a.txt")]);

  attached.forget(attached.ids());

  assert.deepEqual(plain(attached.ids()), []);
  assert.equal(shown.list.hidden, true);
  assert.equal(shown.calls.filter(([url]) => url === "api/detach").length, 0);
  assert.deepEqual(plain(page(shown.store).attach("claude:a").ids()), []);
});

test("a file still uploading shows and keeps the message from going", async () => {
  const shown = page(), attached = shown.attach("claude:a"), release = shown.holdUploads();
  const done = attached.add([file("big.pdf")]);
  await new Promise(r => setImmediate(r));

  assert.equal(attached.busy(), true);
  assert.deepEqual(names(shown.list), ["big.pdf"]);
  assert.equal(part(shown.list.children[0], "size").textContent, "uploading...");
  release();
  await done;
  assert.equal(attached.busy(), false);
});

test("what the server won't take is said and never uploaded", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  await attached.add([{...file("huge.bin"), size: 21 * 1024 * 1024}, {...file("none.txt", ""), size: 0}]);

  assert.deepEqual(shown.said, ["huge.bin is larger than 20 MB", "none.txt is empty"]);
  assert.deepEqual(shown.calls, []);
});

test("files picked together upload in turn and keep the order picked", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  await attached.add([file("b.txt"), file("a.txt")]);

  assert.deepEqual(shown.calls.map(([, args]) => args[0]), ["b.txt", "a.txt"]);
  assert.deepEqual(names(shown.list), ["b.txt", "a.txt"]);
});

test("past ten files the rest are said and left out", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  await attached.add(Array.from({length: 11}, (_, n) => file(`${n}.txt`)));

  assert.equal(attached.ids().length, 10);
  assert.deepEqual(shown.said, ["a message takes at most 10 files"]);
});

test("a file attached while a message was sending stays for the next one", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  await attached.add([file("sent.txt")]);
  const sending = [...attached.ids()];

  await attached.add([file("later.txt")]);
  attached.forget(sending);

  assert.deepEqual(plain(attached.ids()), ["id1"]);
  assert.deepEqual(names(shown.list), ["later.txt"]);
  assert.deepEqual(plain(page(shown.store).attach("claude:a").ids()), ["id1"]);
});

test("a picked image counts as uploading while its thumbnail is still being drawn", async () => {
  const shown = page(), attached = shown.attach("claude:a");
  const done = attached.add([file("photo.png", "png", "image/png")]);
  await new Promise(r => setImmediate(r));

  assert.equal(attached.busy(), true);
  shown.finishDecoding();
  await done;
  assert.equal(attached.busy(), false);
  assert.deepEqual(plain(attached.ids()), ["id0"]);
});
