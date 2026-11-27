(() => {
  // OpenClaw records a long message as its first several thousand characters and this marker; a
  // shorter prefix is a message that happens to end with the marker.
  const cutMarker = "\n...(truncated)...", shortestCut = 1000;
  const holds = (recorded, sent) => {
    const head = recorded.endsWith(cutMarker) ? recorded.slice(0, -cutMarker.length).trimStart() : "";
    if (head.trim().length < shortestCut) return recorded.includes(sent.trim());

    const whole = sent.trim();
    return whole.length > head.length && whole.startsWith(head);
  };
  const said = entries => entries.filter(e => e.role === "user" || e.role === "other");
  const matching = (text, entries) => said(entries).filter(e => holds(e.text, text)).length;
  // Each pending send ({text, seen}, oldest first) takes the first record holding its text after
  // the *seen* that already did when it was sent, and each record is taken once: a record taken by
  // one send counts toward the *seen* of each later send it also holds, so the later one waits
  // for a record of its own. The sends still pending come back with their *seen* brought up to date.
  const unrecorded = (pending, entries) => {
    const records = said(entries);
    const holding = p => records.flatMap((e, i) => holds(e.text, p.text) ? [i] : []);
    const left = pending.map(p => ({...p, seen: p.seen ?? 0}));
    return left.filter((p, at) => {
      const taken = holding(p)[p.seen];
      if (taken === undefined) return true;

      for (const later of left.slice(at + 1)) {
        if (holding(later).indexOf(taken) >= later.seen) later.seen += 1;
      }
      return false;
    });
  };
  // The [at, html] *items*, in the conversation's order, with each of *extra* before the first
  // item later than it; an item without a time stays where it is.
  const inTime = (items, extra) => {
    const left = [...extra].sort((a, b) => Date.parse(a[0]) - Date.parse(b[0]));
    return [...items.flatMap(item => {
      const t = Date.parse(item[0]), before = [];
      while (left.length && !Number.isNaN(t) && Date.parse(left[0][0]) < t) before.push(left.shift());
      return [...before, item];
    }), ...left];
  };
  window.groveSent = {matching, unrecorded, inTime};
})();
