// Deadlock Codex service worker: keeps the page and item/hero art available offline.
var SHELL = "codex-shell-v1", ART = "codex-art-v1", ART_MAX = 700;

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(SHELL).then(function (c) { return c.addAll(["./", "index.html", "manifest.webmanifest", "icon-192.png"]); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== SHELL && k !== ART; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trim(cache) {
  return cache.keys().then(function (keys) {
    if (keys.length <= ART_MAX) return;
    return Promise.all(keys.slice(0, keys.length - ART_MAX).map(function (k) { return cache.delete(k); }));
  });
}

self.addEventListener("fetch", function (e) {
  var r = e.request;
  if (r.method !== "GET") return;
  var u = new URL(r.url);
  if (u.origin === location.origin) {
    // page and app files: newest copy when online, saved copy when not
    e.respondWith(fetch(r).then(function (res) {
      if (res && res.ok) { var copy = res.clone(); caches.open(SHELL).then(function (c) { c.put(r, copy); }); }
      return res;
    }).catch(function () {
      return caches.match(r, { ignoreSearch: true }).then(function (m) {
        if (m) return m;
        if (r.mode === "navigate") return caches.match("index.html");
        return Response.error(); // other files (for example data/*.json) should fail, not return the page
      });
    }));
    return;
  }
  if (u.hostname === "assets-bucket.deadlock-api.com") {
    // game art: saved copy first, fetched once
    e.respondWith(caches.open(ART).then(function (c) {
      return c.match(r).then(function (hit) {
        if (hit) return hit;
        return fetch(r).then(function (res) {
          if (res && (res.ok || res.type === "opaque")) { c.put(r, res.clone()).then(function () { trim(c); }); }
          return res;
        });
      });
    }));
  }
  // everything else (game data, wiki notes) goes straight to the network; the page keeps its own saved copy
});
