self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("findit-static-v1").then((cache) =>
      cache.addAll(["/", "/index.html", "/styles.css", "/app.js", "/manifest.webmanifest", "/icon.svg"])
    )
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
