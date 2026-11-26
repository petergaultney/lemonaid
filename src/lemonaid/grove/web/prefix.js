// The web grove's prefix key (`[web]` in lemonaid's config): the prefix and then the home key (the
// prefix again, by default) go back to the grove from anywhere, a text box included; the prefix and
// then the literal key type the prefix; the prefix and then the brief key focus a lemon's brief, on
// a page that has one. Any other key after the prefix is dropped. On the grove itself, the home key
// goes back to the lemon last shown, as closing the grove window does. A phone's list of groups
// is the grove: a group's list goes up to the groups, and the groups to the last lemon. A phone's
// home button (the lemonaid icon) does what the keys do.
(() => {
  // The lemon page last shown in this browser, for the grove to go back to.
  const lastKey = "lemonaid-last-lemon";
  const onLemon = location.pathname.endsWith("/lemon");
  if (onLemon) { try { localStorage.setItem(lastKey, location.search); } catch {} }
  window.groveHome = () => {
    // Back, when this page was opened from the grove, so the browser shows that page as it was
    // rather than loading it again.
    const from = document.referrer ? new URL(document.referrer) : null;
    if (from && from.origin === location.origin && !from.pathname.endsWith("/lemon") && history.length > 1) history.back();
    else location.href = new URL("./", location.href).href;
  };
  window.groveBack = () => {
    let last = null;
    try { last = localStorage.getItem(lastKey); } catch {}
    if (last) location.href = new URL(`lemon${last}`, location.href).href;
  };
  // What the home keys do here. A lemon's page asks a phone's list for its groups, not the group
  // the lemon was opened from (`groveUp` on that list reads it).
  window.groveKey = () => {
    if (onLemon) {
      try { sessionStorage.setItem("lemonaid-up", "1"); } catch {}
      window.groveHome();
    }
    else if (!(window.groveUp && window.groveUp())) window.groveBack();
  };

  const {prefix, home, literal, brief} = window.groveKeys || {};
  if (!prefix) return;

  const parse = name => {
    const ctrl = name.match(/^C-(.)$/);
    return ctrl ? {ctrl: true, key: ctrl[1].toLowerCase()} : {ctrl: false, key: name === "Space" ? " " : name.toLowerCase()};
  };
  const p = parse(prefix), typed = parse(literal), toBrief = parse(brief || "b");
  const back = home === "prefix" ? p : parse(home);
  const is = (event, k) => event.key.toLowerCase() === k.key && event.ctrlKey === k.ctrl;
  const typeIn = text => {
    const box = document.activeElement;
    if (box && (box.tagName === "TEXTAREA" || box.tagName === "INPUT")) {
      box.setRangeText(text, box.selectionStart, box.selectionEnd, "end");
      box.dispatchEvent(new Event("input", {bubbles: true}));
    }
  };
  let armed = false;
  document.addEventListener("keydown", event => {
    if (event.isComposing || ["Shift", "Control", "Alt", "Meta"].includes(event.key)) return;
    if (!armed && !is(event, p)) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    if (!armed) { armed = true; return; }

    armed = false;
    if (window.groveNote) window.groveNote("prefix", {then: event.key});
    if (is(event, back)) window.groveKey();
    else if (is(event, typed) && !p.ctrl) typeIn(prefix);
    else if (is(event, toBrief)) document.dispatchEvent(new CustomEvent("grove-brief"));
  }, true);
})();
