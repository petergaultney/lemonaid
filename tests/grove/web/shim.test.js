// The web grove's shim (src/lemonaid/grove/web/shim.js), run by `node --test` with stand-ins for the
// browser: the page's calls become requests, and the stream of changes waits for the page.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const shim = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/shim.js"), "utf8");

function browser(hostname = "grove.example", answer = {}) {
  const streams = [], asked = [], fetched = [], ready = {}, shown = {};
  class EventSource {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 0; streams.push(this); }
  }
  const context = {
    EventSource, Event: class { constructor(type) { this.type = type; } }, setInterval: () => 0,
    fetch: async url => { asked.push(url); return {ok: true, json: async () => answer}; },
    document: {addEventListener: (type, then) => { ready[type] = then; }},
    location: {hostname, href: ""},
    window: {
      open: () => {}, dispatchEvent: () => {}, groveData: () => fetched.push(1),
      addEventListener: (type, then) => { shown[type] = then; },
    },
  };
  vm.createContext(context);
  vm.runInContext(shim, context);
  return {api: context.window.pywebview.api, window: context.window, location: context.location, shown, ready, streams, asked, fetched};
}

test("a call reaches the server as a POST to api/<name>", async () => {
  const {api, asked} = browser();

  await api.search("barn");
  assert.deepEqual(asked, ["api/search"]);
});

test("jumping to a lemon in a browser navigates to its page and tells the grove page it is leaving", async () => {
  const {api, window, location, shown} = browser("grove.example", {lemon: "a b"});

  assert.equal(await api.jump("x"), "");
  assert.equal(location.href, "lemon?channel=a%20b");
  assert.equal(window.groveLeaving, true);

  shown.pageshow({persisted: true});
  assert.equal(window.groveLeaving, false, "a page shown again from the browser's cache is no longer leaving");
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

test("in a pywebview window the page keeps the shim's calls and starts once", async () => {
  const listeners = [], docReady = {}, asked = [];
  let starts = 0;
  const window = {
    open: () => {},
    addEventListener: (type, then, capture) => listeners.push({type, then, capture}),
    dispatchEvent: event => {
      let stopped = false;
      event.stopImmediatePropagation = () => { stopped = true; };
      for (const l of [...listeners.filter(l => l.capture), ...listeners.filter(l => !l.capture)]) {
        if (stopped) break;
        if (l.type === event.type) l.then(event);
      }
    },
  };
  const context = {
    EventSource: class { constructor() { this.readyState = 0; } }, setInterval: () => 0,
    Event: class { constructor(type) { this.type = type; } },
    fetch: async url => { asked.push(url); return {ok: true, json: async () => ({})}; },
    document: {addEventListener: (type, then) => { docReady[type] = then; }},
    window,
  };
  vm.createContext(context);
  vm.runInContext(shim, context);
  window.addEventListener("pywebviewready", () => { starts += 1; });  // the page's own start

  docReady.DOMContentLoaded();
  window.pywebview = {api: {}};  // what pywebview puts there once the page has loaded
  window.dispatchEvent({type: "pywebviewready"});
  await window.pywebview.api.search("barn");

  assert.equal(starts, 1);
  assert.deepEqual(asked, ["api/search"]);
});
