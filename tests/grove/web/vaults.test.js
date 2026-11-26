// This device's vault names (src/lemonaid/grove/web/vaults.js), run by `node --test` with stand-ins
// for the page's links: each vault link a page shows takes this device's name for its vault.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../../../src/lemonaid/grove/web/vaults.js"), "utf8");

class Link {
  constructor(href, text) {
    this.nodeType = 1;
    this.attrs = {href};
    this.dataset = {};
    this.childNodes = [text];
    this.replacedBy = null;
  }
  matches(selector) { return selector === "a[href]"; }
  querySelectorAll() { return []; }
  getAttribute(name) { return this.attrs[name]; }
  setAttribute(name, value) { this.attrs[name] = value; }
  replaceWith(node) { this.replacedBy = node; }
}

function page(stored) {
  const observers = [];
  const store = {...stored};
  const context = {
    localStorage: {getItem: key => store[key] ?? null, setItem: (key, value) => { store[key] = value; }},
    document: {
      documentElement: {},
      createElement: () => ({append(...nodes) { this.childNodes = nodes; }}),
    },
    MutationObserver: class { constructor(then) { observers.push(then); } observe() {} },
    window: {},
  };
  vm.createContext(context);
  vm.runInContext(script, context);
  const show = (...links) => { for (const then of observers) then([{addedNodes: links}]); return links; };
  return {show, vaults: context.window.groveVaults, store};
}

test("a vault this device names otherwise opens under its name here", () => {
  const {show} = page({"lemonaid-vaults": JSON.stringify({trove: "My Trove"})});
  const [link] = show(new Link("obsidian://open?vault=trove&file=a%2Fb#Top", "b"));

  assert.equal(link.getAttribute("href"), "obsidian://open?vault=My%20Trove&file=a%2Fb#Top");
});

test("a vault this device doesn't have shows its links as plain text", () => {
  const {show} = page({"lemonaid-vaults": JSON.stringify({work: "-"})});
  const [link] = show(new Link("obsidian://open?vault=work&file=a", "a"));

  assert.equal(link.replacedBy.className, "no-vault");
  assert.deepEqual(link.replacedBy.childNodes, ["a"]);
});

test("a vault the map doesn't name, and every other link, stay as the server wrote them", () => {
  const {show} = page({"lemonaid-vaults": JSON.stringify({trove: "Mine"})});
  const links = show(
    new Link("obsidian://open?vault=work&file=a", "a"),
    new Link("https://example.com/?vault=trove", "b"),
  );

  assert.deepEqual(links.map(link => link.getAttribute("href")), [
    "obsidian://open?vault=work&file=a",
    "https://example.com/?vault=trove",
  ]);
});

test("a link drawn again is rewritten from what the server wrote, not from its last rewrite", () => {
  const {show} = page({"lemonaid-vaults": JSON.stringify({trove: "vault"})});
  const [link] = show(new Link("obsidian://open?vault=trove&file=a", "a"));
  show(link);

  assert.equal(link.getAttribute("href"), "obsidian://open?vault=vault&file=a");
  assert.equal(link.dataset.vaultHref, "obsidian://open?vault=trove&file=a");
});

test("a stored map it can't read leaves links as the server wrote them", () => {
  const {show, vaults} = page({"lemonaid-vaults": "not json"});
  const [link] = show(new Link("obsidian://open?vault=trove&file=a", "a"));

  assert.equal(link.getAttribute("href"), "obsidian://open?vault=trove&file=a");
  assert.deepEqual({...vaults.load()}, {});
});
