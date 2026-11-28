// The grove's service worker: it shows the server's push notifications, and a tap opens the lemon's
// page in the app, in its open window if it has one. It also keeps the phone's pages, icons and the
// two libraries a lemon's page renders with, so the app opens with no network. The server's answers
// (api/) pass by it: a page keeps its own last good answer (talks.js) and draws that.
// Cache names belong to the whole origin, so each grove's are its own by scope, and a new version
// removes only that grove's older caches.
const OURS = `lemonaid-pages ${self.registration.scope} `, PAGES = `${OURS}1`;
const OWN = ["groups", "lemon", "vaults", "settings", "manifest.webmanifest", "icon.svg", "icon-192.png", "apple-touch-icon.png"];
const LIBRARIES = [
  "https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.1.6/purify.min.js",
];
const own = url => new URL(url, self.registration.scope);
const keep = async (key, request) => {
  const r = await fetch(request);
  if (r.ok || r.type === "opaque") await (await caches.open(PAGES)).put(key, r.clone());
  return r;
};
self.addEventListener("install", e => e.waitUntil((async () => {
  // One missing piece shouldn't stop the worker that shows notifications from installing.
  await Promise.allSettled([
    ...OWN.map(path => keep(own(path).href, own(path).href)),
    ...LIBRARIES.map(url => keep(url, new Request(url, {mode: "no-cors"}))),
  ]);
  await self.skipWaiting();
})()));
self.addEventListener("activate", e => e.waitUntil((async () => {
  for (const name of await caches.keys()) if (name.startsWith(OURS) && name !== PAGES) await caches.delete(name);
  await self.clients.claim();
})()));

// A page from the server while it answers, so it's never behind, and the one kept when it doesn't.
// A lemon's page is one page whatever lemon it's for, and the app's start (the scope) is the groups.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;

  const url = new URL(e.request.url);
  if (LIBRARIES.includes(url.href)) {  // versioned, so a kept copy is current
    e.respondWith(caches.open(PAGES).then(c => c.match(url.href, {ignoreVary: true})).then(kept => kept || keep(url.href, e.request)));
    return;
  }
  if (url.origin !== location.origin || !url.href.startsWith(self.registration.scope)) return;

  const path = url.pathname.slice(own(".").pathname.length);
  const key = path === "" ? "groups" : path;
  if (!OWN.includes(key)) return;

  e.respondWith(fetch(e.request).then(async r => {
    if (r.ok && r.type === "basic" && !r.redirected && path === key) await (await caches.open(PAGES)).put(own(key).href, r.clone());
    return r;
  }).catch(async error => (await (await caches.open(PAGES)).match(own(key).href, {ignoreVary: true})) || Promise.reject(error)));
});

// Every push must show a notification, or the browser may show its own or drop the subscription.
// One for a lemon whose page is open and in view comes silently, and that page closes it once it
// has drawn the news (lemon.html).
const showing = async url => {
  const open = await self.clients.matchAll({type: "window"});
  return open.some(c => c.visibilityState === "visible" && c.url === new URL(url, self.registration.scope).href);
};

// A lemon read elsewhere, such as in the desktop inbox, closes its notification and shows nothing.
// Chrome and Firefox allow that now and then, past which Chrome shows its own notice; the server
// sends a clear only after that lemon's news, and never to Safari, which revokes (push/pusher.py).
const clear = async tag => {
  for (const n of await self.registration.getNotifications({tag})) n.close();
};

self.addEventListener("push", e => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch { m = {title: "lemonaid", body: e.data ? e.data.text() : ""}; }
  if (m.clear) return e.waitUntil(clear(m.clear));
  e.waitUntil(showing(m.url || "groups").then(shown => self.registration.showNotification(m.title || "lemonaid", {
    body: m.body || "",
    tag: m.tag || "",
    renotify: Boolean(m.tag) && !shown,  // a lemon's new notification replaces its last and still buzzes
    silent: shown,
    icon: "icon-192.png",
    badge: "badge.png",  // the icon's rind and segments, cut out of white
    data: {url: m.url || "groups"},
  })));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data && e.notification.data.url || "groups", self.registration.scope).href;
  e.waitUntil((async () => {
    const open = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    const mine = open.find(c => c.url.startsWith(self.registration.scope));
    if (mine) {
      await mine.focus();
      try { await mine.navigate(url); return; } catch {}
    }
    await self.clients.openWindow(url);
  })());
});
