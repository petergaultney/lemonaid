// A right-click on a lemon, a tree or a block offers the terminal grove's select-mode edits, and so does
// choosing one from the keyboard after `Tab`; those that need an answer ask for it in a small dialog, and
// Python makes the change (window/edits.py). Each edit has the terminal's letter.
const menu = document.getElementById("menu"), dialog = document.getElementById("dialog");
const EDITS = [["rename", "r", "Rename…"], ["snooze", "s", "Snooze…"], ["archive", "a", "Archive"], ["pin", "p", "Pin or unpin"], ["group", "g", "Move to group…"], ["color", "c", "Recolor block…"]];
const escaped = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const menuOpen = () => menu.style.display === "block", dialogOpen = () => dialog.style.display === "block";
let menuItems = [], menuAt = 0, menuTarget = null;  // the open menu's edits, the highlighted one, and what they change

function closeMenus() {
  menu.style.display = "none"; dialog.style.display = "none";
  if (dialog.contains(document.activeElement)) document.activeElement.blur();  // a hidden field would still take keys
}
function said(text) { document.getElementById("msg").textContent = text || ""; }

// What a right-click is on: one lemon (a row of a list), a whole tree, or a block's ground.
function editTarget(h) {
  if (!h || !h.block) return null;
  if (h.lemon) return {digit: h.block.digit, key: h.tree.key, channel: h.lemon.channel, title: h.lemon.name || h.lemon.session};
  if (h.tree) return {digit: h.block.digit, key: h.tree.key, channel: "", title: `${h.block.digit}${h.tree.letter} ${h.tree.label}`};
  if (h.ground && h.block.group) return {digit: h.block.digit, key: "", channel: "", title: h.block.group, block: true};
  return null;
}
// A block's menu only recolors it; a lemon's or a tree's has the rest.
const editsFor = target => EDITS.filter(([action]) => (action === "color") === !!target.block);

function drawMenu() {
  menu.innerHTML = `<div class="title">${escaped(menuTarget.title)}</div>` + menuItems.map(([action, key, label], i) => {
    const at = label.toLowerCase().indexOf(key), shown = `${escaped(label.slice(0, at))}<span class="key">${escaped(label[at])}</span>${escaped(label.slice(at + 1))}`;
    return `<div class="item${i === menuAt ? " on" : ""}" data-action="${action}">${shown}</div>`;
  }).join("");
  menu.querySelectorAll(".item").forEach(item => item.addEventListener("click", () => choose(item.dataset.action)));
}
function showMenu(x, y, target) {
  menuTarget = target; menuItems = editsFor(target); menuAt = 0;
  drawMenu();
  menu.style.left = Math.min(x, innerWidth - 200) + "px"; menu.style.top = Math.min(y, innerHeight - 30 * menuItems.length - 40) + "px";
  menu.style.display = "block";
}
function choose(action) { menu.style.display = "none"; begin(action, menuTarget); }
// While the menu is open: an edit's letter, or ↑ ↓ and enter, chooses it; esc closes it.
function menuKey(e) {
  const by = menuItems.find(([, key]) => key === e.key);
  if (by) return choose(by[0]);
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { menuAt = (menuAt + (e.key === "ArrowDown" ? 1 : menuItems.length - 1)) % menuItems.length; return drawMenu(); }
  if (e.key === "Enter") return choose(menuItems[menuAt][0]);
  if (e.key === "Escape" || e.key === "Tab") menu.style.display = "none";
}

// `Tab` chooses from the keyboard, as the terminal grove's select mode does: a block's digit, then a
// tree's letter for its first lemon, `.s1` for another, `$` and a letter for the whole tree, or `#` for
// the block. The choice opens its menu beside it.
function menuBeside(target, on) {
  const h = hits.find(on) || hits.find(h => h.block && h.block.digit === target.digit && h.ground), r = cv.getBoundingClientRect();
  showMenu(r.left + (h ? h.x + Math.min(h.w, 60) : 40), r.top + (h ? h.y + h.h : 40), target);
}
function selectKey(e) {
  const was = selecting, b = zoomed && DATA.blocks.find(b => b.digit === zoomed);
  if (!/^[0-9]$/.test(e.key) || was.letter) typed = "";  // only digits build a block's number
  if (e.key === "Tab" || e.key === "Escape") { selecting = null; return draw(); }
  if (e.key === "Backspace") {  // a choice under way, then back to the view select mode began in, then out of it
    if (was.mode) selecting = {mode: ""};
    else if (zoomed !== selectFrom) goTo(selectFrom);
    else selecting = null;
    return draw();
  }
  if (/^[0-9]$/.test(e.key) && !was.letter) {  // a block's number, as the page's own keys build one: 1 then 2 is block 12
    selecting = {mode: ""}; typed = (typed + e.key).slice(-2);
    return zoomTo(DATA.blocks.some(b => b.digit === typed) ? typed : e.key);
  }
  if (!b) { said("type a block's digit first"); return; }

  selecting = {mode: ""};
  if (e.key === "#" && b.group) return menuBeside({digit: b.digit, key: "", channel: "", title: b.group, block: true}, () => false);
  if (e.key === "$" || e.key === ".") { selecting = {mode: e.key}; return status(); }
  const t = was.letter ? b.trees.find(t => t.letter === was.letter) : b.trees.find(t => t.letter === e.key);
  if (!t) { status(); return said(`no tree ${b.digit}${was.letter || e.key}`); }
  if (was.mode === "$") return menuBeside({digit: b.digit, key: t.key, channel: "", title: `${b.digit}${t.letter} ${t.label}`}, h => h.tree === t && !h.lemon);
  if (was.mode === "." && !was.letter) {
    if (t.lemons.length < 2) { status(); return said("that tree has one lemon: its letter alone chooses it"); }
    selecting = {mode: ".", letter: e.key, num: ""};
    return status();
  }
  const num = (was.num || "") + e.key, i = was.letter ? lemonIndex(num) : 0;
  if (was.letter && num === "0" && t.lemons.length > 10) { selecting = {...was, num}; return status(); }
  if (i === null || i >= t.lemons.length) { status(); return said(`no lemon .${t.letter}${num} on this tree`); }
  const l = t.lemons[i];
  status();
  menuBeside({digit: b.digit, key: t.key, channel: l.channel, title: l.name || l.session}, h => h.lemon === l);
}

function edit(action, target, answer) {
  closeMenus();
  window.pywebview.api.edit(action, target.digit, target.key, target.channel, answer).then(said);
}

async function begin(action, target) {
  if (action === "archive" || action === "pin") return edit(action, target, "");

  const info = await window.pywebview.api.edit_info(action, target.digit, target.key, target.channel);
  if (info.problem) return said(info.problem);

  const field = (value, hint) => `<input id="answer" value="${escaped(value)}" placeholder="${escaped(hint)}" spellcheck="false">`;
  const choices = list => list.map(([value, label]) => `<div class="item" data-value="${escaped(value)}">${escaped(label)}</div>`).join("");
  const body = {
    rename: field(info.name, "a name; empty clears a lemon's"),
    color: field(info.color, "#rrggbb or a name like teal; empty clears"),
    snooze: field("", info.syntax) + choices(info.presets),
    group: info.groups.length ? choices(info.groups.map(g => [g, g])) : "<div>No other group to move to.</div>",
  }[action];
  dialog.innerHTML = `<div class="title">${escaped(info.what)}</div>${body}<div class="hint">enter to change · esc to cancel</div>`;
  dialog.style.display = "block";
  dialog.querySelectorAll(".item").forEach(item => item.addEventListener("click", () => edit(action, target, item.dataset.value)));
  const input = dialog.querySelector("#answer");
  if (input) { input.focus(); input.select(); }
  dialog.onkeydown = ev => {  // kept from the page's own keys, which would act on them again
    if (!dialogOpen()) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeMenus(); }
    else if (ev.key === "Enter" && input) { ev.preventDefault(); ev.stopPropagation(); edit(action, target, input.value.trim()); }
  };
}

cv.addEventListener("contextmenu", e => {
  e.preventDefault();
  closeMenus();
  const r = cv.getBoundingClientRect(), target = editTarget(hitAt(e.clientX - r.left, e.clientY - r.top));
  if (target) { hideCard(); showMenu(e.clientX, e.clientY, target); }
});
document.addEventListener("pointerdown", e => { if (menuOpen() && !menu.contains(e.target)) menu.style.display = "none"; }, true);

// `?` lists the keys of the view you're in; any key closes the list.
const help = document.getElementById("help"), helpOpen = () => help.style.display === "block";
function showHelp() {
  const rows = [
    ...(zoomed ? [["a letter", "jump to that tree's first lemon"], [".s1", "another lemon on tree s: 1 is the second, 0a the eleventh"], [". .", "back to this block's fit"], ["drag a tree", "move it within its block"], ["drag a bare tree", "move it, or off its block's ground to clear it"]]
      : [["a digit", "zoom into that block"], ["click a tree", "jump to its first lemon"], [".", "back to the grove's fit"], ["drag a block", "move it, or by its edge resize it; open ground too"]]),
    ["click a lemon's row", "jump to that lemon; on its other page, a PR number opens the PR"],
    ["right-click", "a lemon's, tree's or block's edits: rename, snooze, archive, pin, move to a group; recolor a block"],
    ["tab", zoomed ? "choose from the keyboard: a letter, .s1, $ and a letter for the whole tree, or # for the block; then its edit's letter" : "choose from the keyboard: a block's digit first"],
    ["/", "search Brief-IDs, sessions and names; ↑ ↓ choose, enter jumps"],
    [`hold ${flipKey}`, zoomed ? "each lemon's PRs, branch, model and context" : "each tree's mid-turn lemons, fullest context and latest report"],
    ["- +", "smaller or larger labels in this view"],
    [usageKey, "usage"],
    ["esc, backspace", zoomed ? "back to the grove" : "close the window, as q and space do"],
  ];
  help.innerHTML = `<h1>Keys</h1><table>${rows.map(([k, what]) => `<tr><th>${escaped(k)}</th><td>${escaped(what)}</td></tr>`).join("")}</table>`;
  help.style.display = "block";
}
