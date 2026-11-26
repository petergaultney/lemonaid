// The page's notes for the server's log of what browsers did (grove/web/notes.py): its screen,
// its errors, and what was pressed or touched, so a misbehaving page can be explained afterward.
// Keys pressed in a text box are never noted. `window.groveNote` lets the other scripts add theirs.
(() => {
  const tab = Math.random().toString(36).slice(2, 8);  // one page load, to tell interleaved tabs apart
  const page = location.pathname.split("/").pop() || "grove";
  let queue = [], timer = null;
  const flush = () => {
    timer = null;
    if (!queue.length) return;
    const body = JSON.stringify(queue);
    queue = [];
    fetch("api/note", {method: "POST", headers: {"Content-Type": "application/json"}, body, keepalive: true}).catch(() => {});
  };
  const note = (what, detail = {}) => {
    queue.push({what, tab, page, ...detail});
    if (queue.length >= 20) flush();
    else if (!timer) timer = setTimeout(flush, 2000);
  };
  window.groveNote = note;

  // With what the screen shows of the page (the visual viewport) and where the page's bottom bar is,
  // when it has one, to explain a bar that ends up off the screen.
  const screenNow = () => {
    const shown = window.visualViewport, bar = document.querySelector("nav");
    const box = bar && bar.getBoundingClientRect();
    return {
      w: innerWidth, h: innerHeight, dpr: devicePixelRatio, touch: navigator.maxTouchPoints > 0,
      ...(shown ? {shown: [Math.round(shown.height), Math.round(shown.offsetTop)]} : {}),
      ...(box ? {bar: [Math.round(box.top), Math.round(box.bottom)]} : {}),
    };
  };
  note("load", {...screenNow(), url: location.pathname + location.search, ua: navigator.userAgent});
  let resized = null;
  addEventListener("resize", () => { clearTimeout(resized); resized = setTimeout(() => note("resize", screenNow()), 500); });
  if (window.visualViewport) visualViewport.addEventListener("resize", () => { clearTimeout(resized); resized = setTimeout(() => note("resize", screenNow()), 500); });
  addEventListener("pageshow", e => { if (e.persisted) setTimeout(() => note("shown", {...screenNow(), back: true}), 500); });
  addEventListener("error", e => note("error", {message: String(e.message), at: `${e.filename}:${e.lineno}:${e.colno}`}));
  addEventListener("unhandledrejection", e => note("rejected", {message: String((e.reason && e.reason.stack) || e.reason)}));
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });

  // What was pressed: a key's name outside text boxes, and how the screen was touched or clicked.
  const typing = el => el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.isContentEditable);
  document.addEventListener("keydown", e => {
    if (!typing(e.target)) note("key", {key: e.key, ctrl: e.ctrlKey, meta: e.metaKey});
  }, true);
  let lastPointer = 0;
  document.addEventListener("pointerdown", e => {
    if (Date.now() - lastPointer < 500) return;
    lastPointer = Date.now();
    note("pointer", {type: e.pointerType, x: Math.round(e.clientX), y: Math.round(e.clientY), on: e.target.id || e.target.tagName});
  }, true);
  addEventListener("wheel", e => note("wheel", {dy: Math.round(e.deltaY), ctrl: e.ctrlKey}), {passive: true, once: true});
})();
