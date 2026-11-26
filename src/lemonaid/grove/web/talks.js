// The conversations a phone keeps, so a lemon's page draws the last one it had at once and then
// asks for what changed. The list of groups reads ahead the bar's lemons and the lemon last opened,
// once each time one reports, with one request each and no stream kept open for any of them.
(() => {
  const KEY = "lemonaid-talk:", KEPT = 12;  // the most conversations kept, newest first
  const read = channel => { try { return JSON.parse(localStorage.getItem(KEY + channel)); } catch { return null; } };
  const write = (channel, talk, updated) => {
    try {
      localStorage.setItem(KEY + channel, JSON.stringify({talk, updated, at: Date.now()}));
      const kept = Object.keys(localStorage).filter(k => k.startsWith(KEY))
        .map(k => [k, (JSON.parse(localStorage.getItem(k)) || {}).at || 0])
        .sort((x, y) => y[1] - x[1]);
      for (const [k] of kept.slice(KEPT)) localStorage.removeItem(k);
    } catch {}  // without storage, a page just waits for its conversation
  };
  const usable = talk => talk && !talk.error && !talk.conversation_problem;

  window.groveTalks = {
    kept: channel => read(channel)?.talk || null,
    // A conversation just read is current as of now, so a report from before now needn't read it again.
    keep: (channel, talk) => { if (usable(talk)) write(channel, talk, Date.now() / 1000); },
    // *lemons* are [{channel, updated}], `updated` in epoch seconds as the grove's data has it.
    ahead: async lemons => {
      for (const l of lemons) {
        if ((read(l.channel)?.updated || 0) >= l.updated) continue;
        try {
          const r = await fetch("api/talk", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify([l.channel])});
          if (!r.ok) throw new Error(`talk: HTTP ${r.status}`);
          const talk = await r.json();
          if (usable(talk)) write(l.channel, talk, l.updated);
        } catch (e) {
          if (window.groveNote) window.groveNote("problem", {message: `reading ahead ${l.channel}: ${e}`});
        }
      }
    },
  };
})();
