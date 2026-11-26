// The web grove's shim (src/lemonaid/grove/web/shim.js), run by `node --test` with stand-ins for the
// browser: the page's calls become requests, and the stream of changes waits for the page.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const shim = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/shim.js"), "utf8");

function browser() {
  const streams = [], asked = [], fetched = [], ready = {};
  class EventSource {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 0; streams.push(this); }
  }
  const context = {
    EventSource, Event: class { constructor(type) { this.type = type; } }, setInterval: () => 0,
    fetch: async url => { asked.push(url); return {ok: true, json: async () => ({})}; },
    document: {addEventListener: (type, then) => { ready[type] = then; }},
    window: {open: () => {}, dispatchEvent: () => {}, addEventListener: () => {}, groveData: () => fetched.push(1)},
  };
  vm.createContext(context);
  vm.runInContext(shim, context);
  return {api: context.window.pywebview.api, ready, streams, asked, fetched};
}

test("a call reaches the server as a POST to api/<name>", async () => {
  const {api, asked} = browser();

  await api.search("barn");
  assert.deepEqual(asked, ["api/search"]);
});

test("the stream of changes waits for the page's own first call for the grove", async () => {
  const {api, ready, streams, fetched} = browser();

  ready.DOMContentLoaded();
  await api.look();
  await api.settings();
  assert.equal(streams.length, 0, "a stream open before the page measured its window fetched the grove too soon");

  await api.data();
  await api.data();
  assert.deepEqual(streams.map(s => s.url), ["api/changes"]);
  streams[0].onmessage();
  assert.equal(fetched.length, 1);
});

test("the grove page's first call asks for everything it starts with at once", async () => {
  const {api, asked} = browser();

  const look = api.look();
  assert.deepEqual(asked, ["api/look", "api/settings", "api/data"]);
  await look;
  await api.settings();
  await api.data();
  assert.equal(asked.length, 3);

  await api.data();
  assert.deepEqual(asked.slice(3), ["api/data"]);
});
