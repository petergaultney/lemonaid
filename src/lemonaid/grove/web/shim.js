// The grove window's page calls Python as `window.pywebview.api.<name>(...)`. In a browser each call is
// a POST to the server that served the page. Placing the window has no meaning here, and links open in
// this browser. Jumping to a lemon opens its page, except in a browser on the server, which switches the
// server's terminal as the window does; leaving the grove goes back to the lemon page last shown.
(() => {
  // The window has Python push the grove. Here the server says when it changed, over a stream that
  // the browser reopens by itself; while it's closed, the page asks every few seconds. Both start
  // with the page's own first call for the grove, which comes once it has measured its window and
  // read its saved views: a grove that came sooner would be fitted to a canvas of no size.
  let changes = null;
  const fetchGrove = () => window.groveData && window.groveData();
  let polling = null;
  const listen = () => {
    changes = new EventSource("api/changes");
    changes.onmessage = fetchGrove;
    changes.onopen = fetchGrove;  // whatever changed while it was closed
    polling ??= setInterval(() => { if (changes.readyState !== EventSource.OPEN) fetchGrove(); }, 3000);
  };
  // Leaving the page closes its stream, so the browser may keep the page to show again as it was
  // when you come back, and the stream opens again then.
  window.addEventListener("pagehide", () => { if (changes) changes.close(); });
  window.addEventListener("pageshow", event => {
    window.groveLeaving = false;
    if (event.persisted && changes) listen();
  });
  const post = async (name, args) => {
    const r = await fetch(`api/${name}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(args)});
    if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
    return r.json();
  };
  // The grove page asks for these one after another as it starts. Asking for them all with the first
  // saves the round trips between, which a distant browser waits on before it sees the grove.
  const STARTUP = ["look", "settings", "data"], early = {};
  const call = (name, args) => {
    if (name === "data" && !changes) listen();
    if (name === STARTUP[0] && !(name in early)) for (const each of STARTUP) early[each] = post(each, []);
    const asked = early[name];
    if (asked) { early[name] = null; return asked; }
    return post(name, args);
  };
  const open = url => { if (/^https?:\/\//.test(url)) window.open(url, "_blank", "noopener"); };
  const here = {
    open_link: async url => open(url),
    jump: async channel => {
      if (["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)) return call("switch", [channel]);
      if (window.groveNote) window.groveNote("jump", {channel});
      const r = await call("jump", [channel]);
      if (r && r.lemon) { window.groveLeaving = true; location.href = `lemon?channel=${encodeURIComponent(r.lemon)}`; return ""; }
      return r;
    },
    // Leaving the grove (Backspace or Escape at the whole grove, Space, q) goes back to the last lemon.
    dismiss: async () => window.groveBack && window.groveBack(),
    to_terminal: async () => window.groveBack && window.groveBack(),
    drag: async () => {}, stick: async () => {},
  };
  const api = new Proxy({}, {get: (_, name) => here[name] || ((...args) => call(name, args))});
  window.pywebview = {api};
  // In a pywebview window (`grove window remote`), pywebview also puts its own object here and says
  // it's ready: the calls stay this page's, and the page starts once, on whichever
  // comes first.
  let started = false;
  window.addEventListener("pywebviewready", event => {
    window.pywebview.api = api;
    if (started) event.stopImmediatePropagation();
    started = true;
  }, true);
  document.addEventListener("DOMContentLoaded", () => { if (!started) window.dispatchEvent(new Event("pywebviewready")); });
})();
