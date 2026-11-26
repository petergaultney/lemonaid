// A phone's edits of one lemon, the grove's own (window/edits.py), in a sheet from the bottom: opened
// by a lemon's page's edit button, or by holding a lemon in a list. What an edit did, or why it
// didn't, stays in the sheet until it is closed, since the grove's edits answer both in plain words;
// a call that failed outright goes to the server's log too.
(() => {
  const EDITS = [["rename", "Rename"], ["snooze", "Snooze"], ["pin", ""], ["group", "Move to group"], ["archive", "Archive"]];
  const HOLD_MS = 500, SLOP = 10;  // how long a hold is, and how far a finger may move while holding
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  document.head.insertAdjacentHTML("beforeend", `<style>
#edits { position:fixed; inset:0; z-index:10; display:flex; flex-direction:column; justify-content:flex-end; background:#0009; font:15px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
#edits[hidden] { display:none; }
#edits .sheet { display:flex; flex-direction:column; gap:8px; max-height:80%; overflow-y:auto; padding:12px 14px calc(12px + env(safe-area-inset-bottom)); background:#161b24; color:#e6ebf2; border-radius:12px 12px 0 0; }
#edits .title { color:#7c8696; font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#edits button { flex-shrink:0; min-height:48px; padding:0 14px; font:inherit; font-weight:700; text-align:left; background:#2d3442; color:#e6ebf2; border:0; border-radius:8px; }
#edits button.go { text-align:center; background:#f2d94e; color:#0b0e13; }
#edits button.quiet { text-align:center; background:none; color:#7c8696; }
#edits input { font:inherit; font-size:16px; padding:10px; background:#0b0e13; color:#e6ebf2; border:1px solid #3a4250; border-radius:8px; }
#edits .said { padding:4px 0; color:#e6ebf2; }
#edits .said.problem { color:#e5534b; }
[data-hold] { -webkit-touch-callout:none; user-select:none; }
</style>`);

  // The browser's TypeError is a request nothing answered, which may still have reached the grove.
  const failure = e => e instanceof TypeError ? `Couldn't reach the grove (${e.message}); check before trying again` : String(e);
  const ask = async (name, args) => {
    const r = await fetch(`api/${name}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(args)});
    if (!r.ok) throw new Error(`${name}: HTTP ${r.status} ${await r.text()}`);
    return r.json();
  };

  let sheet = null, closed = () => {};  // closed: what closing the sheet showing now runs
  const close = () => { if (sheet) sheet.hidden = true; const then = closed; closed = () => {}; then(); };
  const open = html => {
    if (!sheet) {
      sheet = document.createElement("div");
      sheet.id = "edits";
      sheet.addEventListener("click", e => { if (e.target === sheet || e.target.closest("[data-close]")) close(); });
      document.body.appendChild(sheet);
    }
    closed = () => {};
    sheet.innerHTML = `<div class="sheet">${html}</div>`;
    sheet.hidden = false;
    return sheet;
  };

  const say = (text, problem, then = () => {}) => {
    open(`<div class="said${problem ? " problem" : ""}">${esc(text)}</div><button class="quiet" data-close>OK</button>`);
    closed = then;
    if (problem && window.groveNote) window.groveNote("problem", {message: text});
  };

  async function make(action, lemon, answer, after) {
    let done;
    try { done = await ask("lemon_edit", [action, lemon.channel, answer]); } catch (e) { return say(failure(e), true); }
    say(done.said, false, () => after(done));
  }

  async function begin(action, lemon, after) {
    if (action === "pin" || action === "archive") return make(action, lemon, "", after);

    let info;
    try { info = await ask("lemon_edit_info", [action, lemon.channel]); } catch (e) { return say(failure(e), true); }
    if (info.problem) return say(info.problem, true);

    const field = (value, hint) => `<input value="${esc(value)}" placeholder="${esc(hint)}" spellcheck="false" autocapitalize="off" enterkeyhint="done">`;
    const choices = list => list.map(([value, label]) => `<button data-value="${esc(value)}">${esc(label)}</button>`).join("");
    const body = {
      rename: field(info.name, "a name; empty clears it"),
      snooze: choices(info.presets) + field("", info.syntax),
      group: info.groups.length ? choices(info.groups.map(g => [g, g])) : '<div class="said">No other group to move to.</div>',
    }[action];
    const label = EDITS.find(([a]) => a === action)[1];
    const s = open(`<div class="title">${esc(info.what)}</div>${body}`
      + (action === "group" ? "" : `<button class="go" data-go>${esc(label)}</button>`) + '<button class="quiet" data-close>Cancel</button>');
    const input = s.querySelector("input"), go = () => make(action, lemon, input.value.trim(), after);
    s.querySelectorAll("[data-value]").forEach(b => { b.onclick = () => make(action, lemon, b.dataset.value, after); });
    s.querySelector("[data-go]")?.addEventListener("click", go);
    if (input) input.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); go(); } };
    if (action === "rename") { input.focus(); input.select(); }
  }

  // *lemon* is {channel, name, pinned}; *after({said, gone})* runs once what an edit did is read
  // and closed.
  window.groveEdit = (lemon, after = () => {}) => {
    const s = open(`<div class="title">${esc(lemon.name)}</div>`
      + EDITS.map(([action, label]) => `<button data-action="${action}">${action === "pin" ? (lemon.pinned ? "Unpin" : "Pin") : label}</button>`).join("")
      + '<button class="quiet" data-close>Cancel</button>');
    s.querySelectorAll("[data-action]").forEach(b => { b.onclick = () => begin(b.dataset.action, lemon, after); });
  };

  // Holding anything marked data-hold calls *held(element)* in place of the browser's own menu for
  // it, and the tap that ends the hold doesn't follow its link. Moving the finger, as to scroll, isn't
  // a hold.
  window.groveHold = held => {
    let timer = null, at = null, fired = false;
    const fire = el => { clearTimeout(timer); timer = null; fired = true; held(el); };
    document.addEventListener("pointerdown", e => {
      const el = e.target.closest("[data-hold]");
      fired = false;
      if (!el) return;
      at = [e.clientX, e.clientY];
      timer = setTimeout(() => fire(el), HOLD_MS);
    });
    document.addEventListener("pointermove", e => {
      if (timer && Math.hypot(e.clientX - at[0], e.clientY - at[1]) > SLOP) { clearTimeout(timer); timer = null; }
    });
    for (const end of ["pointerup", "pointercancel"]) document.addEventListener(end, () => { clearTimeout(timer); timer = null; });
    document.addEventListener("contextmenu", e => {  // Android's long press, and a right-click
      const el = e.target.closest("[data-hold]");
      if (!el) return;
      e.preventDefault();
      if (!fired) fire(el);
    });
    document.addEventListener("click", e => {
      if (!fired) return;
      fired = false;
      e.preventDefault();
      e.stopPropagation();
    }, true);
  };
})();
