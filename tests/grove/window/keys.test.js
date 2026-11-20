// The window's key helpers (src/lemonaid/grove/window/static/keys.js), run by `node --test`.
const test = require("node:test");
const assert = require("node:assert/strict");
const {lemonIndex, searchBlock, searchStep} = require("../../../src/lemonaid/grove/window/static/keys.js");

test("a lemon's place counts as the terminal grove's does", () => {
  assert.deepEqual(["1", "9", "0a", "0c"].map(lemonIndex), [1, 9, 10, 12]);
  assert.deepEqual(["0", "10", "a", "0A", ""].map(lemonIndex), [null, null, null, null, null]);
});

test("a search zooms only when every match is in one block", () => {
  assert.equal(searchBlock([{digit: "2"}, {digit: "2"}]), "2");
  assert.equal(searchBlock([{digit: "2"}, {digit: "3"}]), "");
  assert.equal(searchBlock([]), "");
});

test("a search takes text, chooses around its matches, and closes or jumps", () => {
  const found = [{digit: "1"}, {digit: "2"}, {digit: "3"}];
  let s = {text: "", found: [], chosen: 0};

  s = searchStep(s, "o");
  assert.deepEqual([s.text, s.ask], ["o", true]);
  s = {...searchStep(s, "q"), found};
  assert.equal(s.text, "oq");  // keys that act elsewhere are text here
  assert.equal(searchStep(s, "ArrowUp").chosen, 2);
  assert.equal(searchStep(searchStep(s, "ArrowDown"), "ArrowDown").chosen, 2);
  assert.equal(searchStep(s, "Backspace").text, "o");
  assert.deepEqual([searchStep(s, "Enter").close, searchStep(s, "Enter").jump], [true, true]);
  assert.equal(searchStep(s, "Escape").jump, undefined);
  assert.equal(searchStep({text: "", found: [], chosen: 0}, "Backspace").close, true);
  assert.equal(searchStep(s, "Shift"), s);
});
