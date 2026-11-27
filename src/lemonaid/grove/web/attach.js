// Files attached to the message being written on a lemon's page. Each uploads as soon as it is
// picked (`api/attach`), and the draft keeps its id, name and size in this browser beside the typed
// text, so leaving or reloading the page keeps them. Sending passes the ids with the text (`api/say`).
(() => {
  const MAX_BYTES = 20 * 1024 * 1024, MAX_FILES = 10;  // the server's limits (attachments.py)
  const base64 = async file => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let out = "";
    for (let i = 0; i < bytes.length; i += 0x8000) out += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(out);
  };
  const size = n => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;

  // *list* is the element that shows the attachments; *say* puts a line where the page reports.
  window.groveAttach = (channel, list, say) => {
    const key = `lemonaid-attached:${channel}`;
    let kept = (() => { try { return JSON.parse(localStorage.getItem(key)) || []; } catch { return []; } })();
    let uploading = [];
    const save = () => {
      try { if (kept.length) localStorage.setItem(key, JSON.stringify(kept)); else localStorage.removeItem(key); } catch {}
    };
    const chip = (file, onRemove) => {
      const each = document.createElement("span");
      each.className = onRemove ? "chip" : "chip uploading";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = file.name;
      const note = document.createElement("span");
      note.className = "size";
      note.textContent = onRemove ? size(file.size) : "uploading...";
      each.append(name, note);
      if (onRemove) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.title = remove.ariaLabel = `remove ${file.name}`;
        remove.addEventListener("click", onRemove);
        each.append(remove);
      }
      return each;
    };
    const draw = () => {
      list.replaceChildren(...kept.map(f => chip(f, () => drop(f.id))), ...uploading.map(u => chip(u, null)));
      list.hidden = !kept.length && !uploading.length;
    };
    const drop = id => {
      kept = kept.filter(f => f.id !== id);
      save();
      draw();
      fetch("api/detach", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify([id])})
        .catch(e => window.groveNote && window.groveNote("problem", {message: `detach: ${e}`}));
    };
    // One at a time, in the order picked, so the draft lists them that way; all show at once.
    const upload = async entry => {
      const {file} = entry;
      try {
        const r = await fetch("api/attach", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify([file.name, file.type || "", await base64(file)]),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status} ${await r.text()}`);
        const got = await r.json();
        if (typeof got === "string") say(got);
        else kept = [...kept, got];
      } catch (e) {
        say(`${file.name} didn't upload: ${e}`);
      } finally {
        uploading = uploading.filter(u => u !== entry);
        save();
        draw();
      }
    };
    const add = async files => {
      const queued = [];
      for (const file of files) {
        if (kept.length + uploading.length + queued.length >= MAX_FILES) { say(`a message takes at most ${MAX_FILES} files`); break; }
        if (file.size > MAX_BYTES) say(`${file.name} is larger than ${MAX_BYTES / 1048576} MB`);
        else if (!file.size) say(`${file.name} is empty`);
        else queued.push({name: file.name, size: file.size, file});
      }
      uploading = [...uploading, ...queued];
      draw();
      for (const entry of queued) await upload(entry);
    };
    draw();
    return {
      add: files => add([...files]),
      ids: () => kept.map(f => f.id),
      files: () => kept.map(({name, size}) => ({name, size})),
      busy: () => uploading.length > 0,
      // After a send, the files it took: the server keeps them, for the lemon to read.
      forget: ids => { kept = kept.filter(f => !ids.includes(f.id)); save(); draw(); },
    };
  };
})();
