// sw.js - Service Worker Base
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Instalando...');
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activado y listo para operar en segundo plano');
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Deja pasar todas las peticiones a Django con normalidad
    event.respondWith(fetch(event.request));
});