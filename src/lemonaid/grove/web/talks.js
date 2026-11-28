// The conversations a phone keeps, so a lemon's page draws the last one it had at once and then
// asks for what changed, and has something to show with no network. The list of groups reads ahead
// the bar's lemons and the lemon last opened, once each time one reports, with one request each and
// no stream kept open for any of them. Each answer replaces the one kept before it.
(() => {
  const KEY = "lemonaid-talk:", KEPT = 12;  // the most conversations kept, newest first
  const read = channel => { try { return JSON.parse(localStorage.getItem(KEY + channel)); } catch { return null; } };
  // *at*: when its conversation was read, for the page to say how old it is.
  const write = (channel, kept) => {
    try {
      const was = read(channel) || {};
      localStorage.setItem(KEY + channel, JSON.stringify({...was, ...kept, at: kept.talk ? Date.now() : was.at || Date.now()}));
      const all = Object.keys(localStorage).filter(k => k.startsWith(KEY))
        .map(k => [k, (JSON.parse(localStorage.getItem(k)) || {}).at || 0])
        .sort((x, y) => y[1] - x[1]);
      for (const [k] of all.slice(KEPT)) localStorage.removeItem(k);
    } catch {}  // without storage, a page just waits for its conversation
  };
  const usable = answer => answer && !answer.error && !answer.conversation_problem;

  // The app opens with no network once its service worker has kept its pages (sw.js).
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(e => {
    if (window.groveNote) window.groveNote("problem", {message: `service worker: ${e}`});
  });

  window.groveTalks = {
    kept: channel => read(channel)?.talk || null,
    // The lemon's page as last drawn (its name, status and brief), and its name alone when only
    // its conversation was read ahead.
    keptView: channel => read(channel)?.view || null,
    keptName: channel => read(channel)?.name || "",
    // When the conversation kept for *channel* was read, in epoch milliseconds.
    keptAt: channel => read(channel)?.at || 0,
    // A conversation just read is current as of now, so a report from before now needn't read it again.
    keep: (channel, talk) => { if (usable(talk)) write(channel, {talk, updated: Date.now() / 1000}); },
    keepView: (channel, view) => { if (usable(view)) write(channel, {view}); },
    // What a page says while it shows what it kept: "offline, as of 9:14", with the day if not today.
    offline: at => {
      const d = new Date(at), today = d.toDateString() === new Date().toDateString();
      const shown = d.toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
      return `offline, as of ${today ? shown : `${d.toLocaleDateString([], {month: "short", day: "numeric"})} ${shown}`}`;
    },
    // *lemons* are [{channel, name, updated}], `updated` in epoch seconds as the grove's data has it.
    ahead: async lemons => {
      for (const l of lemons) {
        if ((read(l.channel)?.updated || 0) >= l.updated) continue;
        try {
          const r = await fetch("api/talk", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify([l.channel])});
          if (!r.ok) throw new Error(`talk: HTTP ${r.status}`);
          const talk = await r.json();
          if (usable(talk)) write(l.channel, {talk, updated: l.updated, name: l.name});
        } catch (e) {
          if (window.groveNote) window.groveNote("problem", {message: `reading ahead ${l.channel}: ${e}`});
        }
      }
    },
  };
})();
