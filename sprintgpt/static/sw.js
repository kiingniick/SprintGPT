// SprintGPT service worker: caches the app shell and static assets so the app
// loads fast and can be installed to a phone's home screen.
// Bump CACHE whenever static assets change so clients pick up the new version.
const CACHE = "sprintgpt-v14";
const ASSETS = [
  "/static/style.css",
  "/static/icon.svg",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // Stale-while-revalidate for our own static assets: serve the cached copy for
  // speed, but refresh it in the background so edits (e.g. CSS) appear next load.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.open(CACHE).then((c) =>
        c.match(req).then((cached) => {
          const network = fetch(req).then((res) => {
            c.put(req, res.clone());
            return res;
          }).catch(() => cached);
          return cached || network;
        })
      )
    );
    return;
  }

  // Network-first for pages (data must stay fresh), fall back to cache offline.
  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req))
  );
});
