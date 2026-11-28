// A phone page's bottom bar: the lemonaid button, then as many lemons as the screen is wide enough
// for, the pinned ones in the inbox's order and then the ones that last had a message. The page puts
// a <nav id="nav"> last in its body and draws into it.
(() => {
  const STATUS = {alert:"#e5534b", blocked:"#f2c14e", merge:"#5fbf6a", approve:"#c58af9", review:"#a8794f", running:"#39b5a8", done:"#5a8dee"};
  const RECENT = "lemonaid-recent";  // the bar's unpinned places, by channel, on this device
  const SLOT = 88;  // a bar button's narrowest, with its gap
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})[c]);
  document.head.insertAdjacentHTML("beforeend", `<style>
nav { flex-shrink:0; }
nav:empty { display:none; }
nav { display:flex; gap:8px; padding:8px 10px calc(8px + env(safe-area-inset-bottom)); background:#161b24; }
nav > * { flex:1 1 0; min-width:0; display:flex; align-items:center; justify-content:center; min-height:48px; box-sizing:border-box; border-radius:8px; font-weight:700; }
nav > a { background:#2d3442; color:inherit; text-decoration:none; }
nav > a.home { flex:0 0 52px; background:none; border:2px solid #2d3442; }
nav > a.home img { width:30px; height:30px; }
nav > a.home.none { opacity:0.4; }
nav .lemon { position:relative; font-size:12px; line-height:1.25; text-align:center; color:#aab3c0; font-weight:600; border-bottom:3px solid transparent; }
nav .lemon .busy { position:absolute; top:6px; left:6px; width:7px; height:7px; border-radius:50%; background:#e6ebf2; animation:bar-pulse 1.6s ease-in-out infinite; }
nav .label { min-width:0; padding:0 6px; overflow:hidden; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow-wrap:anywhere; }
nav .lemon .badge { position:absolute; top:5px; right:5px; width:9px; height:9px; border-radius:50%; background:#f2d94e; }
nav .lemon.new { color:#f4f6fa; font-weight:800; }
@keyframes bar-pulse { 50% { opacity:0.35; } }
</style>`);

  const placed = () => { try { return JSON.parse(localStorage.getItem(RECENT)) || []; } catch { return []; } };
  const place = channels => { try { localStorage.setItem(RECENT, JSON.stringify(channels)); } catch {} };

  // Each unpinned lemon keeps its place while it is among them, so a lemon that newly has a message
  // takes the place of the one that has gone longest without. A pinned lemon the grove doesn't show
  // keeps its place empty.
  const lemons = (blocks, pins, count) => {
    const all = blocks.flatMap(b => b.trees.flatMap(t => t.lemons));
    const pinned = pins.slice(0, count).map(channel => all.find(l => l.channel === channel) || null);
    const room = count - pinned.length;
    const recent = all.filter(l => !pins.includes(l.channel)).sort((x, y) => y.updated - x.updated).slice(0, room);
    const before = placed();
    const kept = Array.from({length: room}, (_, i) => recent.find(l => l.channel === before[i]) || null);
    const newcomers = recent.filter(l => !kept.includes(l));
    const places = kept.map(l => l || newcomers.shift() || null);
    place(places.map(l => l ? l.channel : ""));
    return [...pinned, ...places];
  };

  // *home* says where the lemonaid button goes (prefix.js's `groveKey`), or "" when nowhere, which dims it.
  const draw = (blocks, pins, home) => {
    const shown = lemons(blocks, pins, Math.max(2, Math.min(7, Math.floor((innerWidth - 80) / SLOT))));
    const buttons = shown.map(l => !l ? "<span></span>"
      : `<a class="lemon${l.unread ? " new" : ""}" href="lemon?channel=${encodeURIComponent(l.channel)}" data-channel="${esc(l.channel)}" data-hold style="border-bottom-color:${STATUS[l.status] || "transparent"}">${l.working ? '<i class="busy" title="mid-turn"></i>' : ""}${l.unread ? '<i class="badge" title="unread"></i>' : ""}<span class="label">${esc(l.emoji)}${esc(l.name)}</span></a>`);
    const button = `<a class="home${home ? "" : " none"}" href="#" title="${esc(home)}" onclick="event.preventDefault(); window.groveKey()"><img src="icon.svg" alt="lemonaid"></a>`;
    return {html: [button, ...buttons].join(""), lemons: shown};
  };

  window.groveBar = {STATUS, draw};
})();
