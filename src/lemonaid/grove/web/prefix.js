// The web grove's prefix key (`[web]` in lemonaid's config): the prefix and then the home key go
// back to the grove from anywhere, a text box included; the prefix and then the literal key type
// the prefix. Any other key after the prefix is dropped.
(() => {
  const {prefix, home, literal} = window.groveKeys || {};
  if (!prefix) return;

  const parse = name => {
    const ctrl = name.match(/^C-(.)$/);
    return ctrl ? {ctrl: true, key: ctrl[1].toLowerCase()} : {ctrl: false, key: name === "Space" ? " " : name.toLowerCase()};
  };
  const p = parse(prefix), back = parse(home), typed = parse(literal);
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
    if (is(event, back)) location.href = new URL("./", location.href).href;
    else if (is(event, typed) && !p.ctrl) typeIn(prefix);
  }, true);
})();
