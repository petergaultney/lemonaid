// The grove's service worker (src/lemonaid/grove/web/sw.js), run by `node --test`.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/sw.js"), "utf8");
const SCOPE = "https://grove.example/";

const worker = open => {
  const handlers = {}, shown = [], closed = [];
  const self = {
    addEventListener: (name, handler) => { handlers[name] = handler; },
    registration: {scope: SCOPE, showNotification: async (title, options) => { shown.push({title, ...options}); },
      getNotifications: async ({tag}) => [{close: () => closed.push(tag)}]},
    clients: {matchAll: async () => open},
  };
  vm.runInNewContext(script, {self, URL});
  const push = async message => {
    let done;
    handlers.push({data: {json: () => message, text: () => ""}, waitUntil: p => { done = p; }});
    await done;
  };
  return {push, shown, closed};
};

const news = {title: "Ada", body: "done", tag: "claude:ada", url: "lemon?channel=claude%3Aada"};

test("a push with the app closed shows a notification that buzzes", async () => {
  const {push, shown} = worker([]);
  await push(news);
  assert.equal(shown.length, 1);
  assert.equal(shown[0].title, "Ada");
  assert.equal(shown[0].silent, false);
  assert.equal(shown[0].renotify, true);
});

test("a push for the lemon whose page is in view still shows one, silently", async () => {
  const {push, shown} = worker([{visibilityState: "visible", url: `${SCOPE}lemon?channel=claude%3Aada`}]);
  await push(news);
  assert.equal(shown.length, 1);
  assert.equal(shown[0].silent, true);
  assert.equal(shown[0].renotify, false);
});

test("a clear for a lemon read elsewhere closes its notification and shows none", async () => {
  const {push, shown, closed} = worker([]);
  await push({clear: "claude:ada"});
  assert.equal(shown.length, 0);
  assert.deepEqual(closed, ["claude:ada"]);
});
