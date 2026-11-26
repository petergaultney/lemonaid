// The grove window's page calls Python as `window.pywebview.api.<name>(...)`. In a browser each call is
// a POST to the server that served the page. Placing the window has no meaning here, and links open in
// this browser, including a chat room that `jump` answers with.
(() => {
  // The window has Python push the grove. Here the server says when it changed, over a stream that
  // the browser reopens by itself; while it's closed, the page asks every few seconds. Both start
  // with the page's own first call for the grove, which comes once it has measured its window and
  // read its saved views: a grove that came sooner would be fitted to a canvas of no size.
  let changes = null;
  const fetchGrove = () => window.groveData && window.groveData();
  const listen = () => {
    changes = new EventSource("api/changes");
    changes.onmessage = fetchGrove;
    changes.onopen = fetchGrove;  // whatever changed while it was closed
    setInterval(() => { if (changes.readyState !== EventSource.OPEN) fetchGrove(); }, 3000);
  };
  const call = async (name, args) => {
    if (name === "data" && !changes) listen();
    const r = await fetch(`api/${name}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(args)});
    if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
    return r.json();
  };
  const open = url => { if (/^https?:\/\//.test(url)) window.open(url, "_blank", "noopener"); };
  const here = {
    open_link: async url => open(url),
    jump: async channel => {
      const r = await call("jump", [channel]);
      if (r && r.open) { open(r.open); return ""; }
      return r;
    },
    dismiss: async () => {}, to_terminal: async () => {}, drag: async () => {}, stick: async () => {},
  };
  window.pywebview = {api: new Proxy({}, {get: (_, name) => here[name] || ((...args) => call(name, args))})};
  document.addEventListener("DOMContentLoaded", () => window.dispatchEvent(new Event("pywebviewready")));
})();
