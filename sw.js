/* BalanceAI service worker: displays Web Push notifications sent by the server
   (works while the browser is running, even if the BalanceAI tab is closed). */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : "" }; }
  event.waitUntil(self.registration.showNotification(data.title || "BalanceAI", {
    body: data.body || "",
    icon: "/assets/favicon.svg",
    badge: "/assets/favicon.svg",
    tag: data.tag || "balanceai",
    data: { link: data.link || "#home" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = "/" + ((event.notification.data && event.notification.data.link) || "#home");
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) {
      if ("focus" in c) { c.postMessage({ type: "open", link: url }); return c.focus(); }
    }
    return self.clients.openWindow(url);
  }));
});
