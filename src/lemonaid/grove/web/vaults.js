// What each vault the server names is called on this device. The server writes a note's link by its
// vault's name on the server (`obsidian://open?vault=trove&file=...`); this browser may know that
// vault by another name, or not have it. The map lives in this browser, for this grove's address,
// and the vaults page sets it. Every vault link a page shows is rewritten by it as it appears: to
// this device's name, or to plain text when the vault isn't here. A vault the map doesn't name
// keeps the server's name.
(() => {
  const KEY = "lemonaid-vaults";
  const MISSING = "-";
  const load = () => {
    try {
      const map = JSON.parse(localStorage.getItem(KEY) || "{}");
      return map && typeof map === "object" && !Array.isArray(map) ? map : {};
    } catch { return {}; }
  };
  const save = map => {
    try { localStorage.setItem(KEY, JSON.stringify(map)); return true; } catch { return false; }
  };
  const PARAM = /([?&]vault=)([^&#]*)/;
  const vaultOf = href => {
    if (!/^obsidian:\/\/open\?/i.test(href)) return null;
    const found = href.match(PARAM);
    if (!found) return null;
    try { return decodeURIComponent(found[2]); } catch { return null; }
  };
  const rewrite = (link, map) => {
    const written = link.dataset.vaultHref || link.getAttribute("href") || "";
    const vault = vaultOf(written);
    if (vault === null) return;
    link.dataset.vaultHref = written;
    const here = map[vault];
    if (here === MISSING) {
      const text = document.createElement("span");
      text.className = "no-vault";
      text.title = `The vault "${vault}" isn't on this device`;
      text.append(...link.childNodes);
      link.replaceWith(text);
      return;
    }
    link.setAttribute("href", here ? written.replace(PARAM, `$1${encodeURIComponent(here)}`) : written);
  };
  const within = (node, map) => {
    if (node.nodeType !== 1) return;
    if (node.matches("a[href]")) rewrite(node, map);
    for (const link of node.querySelectorAll("a[href]")) rewrite(link, map);
  };
  const map = load();
  new MutationObserver(changes => {
    for (const change of changes) for (const node of change.addedNodes) within(node, map);
  }).observe(document.documentElement, {childList: true, subtree: true});
  window.groveVaults = {load, save, vaultOf, MISSING};
})();
