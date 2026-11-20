// What the window's keys reach, as the terminal grove works it out (tui/keys.py). Pure, so node can
// test it; the page inlines this file ahead of its own script.

// A lemon's place on its tree, typed after `.` and the tree's letter: 1 to 9, then 0 and a letter
// from the eleventh on (`0a`), as draw/lemon_list.py's `lemon_index`.
function lemonIndex(typed) {
  if (/^[1-9]$/.test(typed)) return Number(typed);
  if (/^0[a-z]$/.test(typed)) return 10 + typed.charCodeAt(1) - 97;
  return null;
}

// The block every match of a search stands in, which the view zooms to, or "" when they're spread
// across blocks or there are none.
function searchBlock(found) {
  const digits = new Set(found.map(m => m.digit));
  return digits.size === 1 ? [...digits][0] : "";
}

// What a typed key does while a search is open: its new text and chosen match, and whether it
// closes the search, jumps to the chosen match, or asks Python for matches again.
function searchStep(search, key) {
  const n = search.found.length;
  if (key === "Escape") return {...search, close: true};
  if (key === "Enter") return {...search, close: true, jump: n > 0};
  if (key === "ArrowDown" || key === "ArrowUp") return {...search, chosen: n ? (search.chosen + (key === "ArrowDown" ? 1 : n - 1)) % n : 0};
  if (key === "Backspace") return search.text ? {...search, text: search.text.slice(0, -1), chosen: 0, ask: true} : {...search, close: true};
  if (key.length === 1) return {...search, text: search.text + key, chosen: 0, ask: true};
  return search;
}

if (typeof module !== "undefined") module.exports = {lemonIndex, searchBlock, searchStep};
