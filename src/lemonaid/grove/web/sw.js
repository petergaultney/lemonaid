// The grove's service worker: it shows the server's push notifications, and a tap opens the lemon's
// page in the app, in its open window if it has one. It caches nothing; the pages come from the server.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

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
