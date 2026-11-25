// The grove window's page calls Python as `window.pywebview.api.<name>(...)`. In a browser each call is
// a POST to the server that served the page. Placing the window has no meaning here, and links open in
// this browser, including a chat room that `jump` answers with.
(() => {
  const call = async (name, args) => {
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
  document.addEventListener("DOMContentLoaded", () => {
    window.dispatchEvent(new Event("pywebviewready"));
    setInterval(() => window.groveData && window.groveData(), 3000);  // the window has Python push this
  });
})();
