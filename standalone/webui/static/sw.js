/* Agent Lab service worker — installability, and nothing clever.
 *
 * A service worker is required for the browser to offer "Install app". That is
 * the only reason this exists, so it does the minimum and gets out of the way.
 *
 * DELIBERATELY NOT CACHED:
 *   /api/*   the whole app is a live local server; a stale run status or a
 *            cached workspace listing would be worse than no app at all.
 *   /api/events  an SSE stream. Passing an EventSource through respondWith is
 *                a reliable way to break streaming, so it never reaches here.
 * Anything this worker does not explicitly answer falls through to the network
 * untouched — no respondWith, no interception.
 */
const CACHE = 'agent-lab-v1';
const SHELL = [
  '/',
  '/static/app.js',
  '/static/style.css',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;      // always live

  // Network-first: the server is on loopback, so it is up whenever the app is
  // open. The cache is a fallback for the split second during a server restart,
  // not a performance strategy.
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request).then((hit) => hit || caches.match('/')))
  );
});
