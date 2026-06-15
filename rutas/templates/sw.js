const CACHE_NAME = 'senaletica-cache-v1';

// 1. Archivos estáticos críticos que se descargan la primera vez que abres la app
const URLS_TO_CACHE = [
    '/',
    '/manifest.json',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Urbanist:wght@700&display=swap',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

// INSTALACIÓN: Guardar lo básico en la memoria del teléfono
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Caché abierto. Guardando estructura básica...');
                return cache.addAll(URLS_TO_CACHE);
            })
    );
    self.skipWaiting();
});

// ACTIVACIÓN: Limpiar cachés viejos si actualizas la versión (v2, v3...)
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cache => {
                    if (cache !== CACHE_NAME) {
                        console.log('Borrando caché antiguo:', cache);
                        return caches.delete(cache);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// INTERCEPTOR DE PETICIONES (El corazón del modo Offline)
self.addEventListener('fetch', event => {
    const peticion = event.request;
    const url = new URL(peticion.url);

    // Estrategia 1: Para la API de los buses (Coordenadas en vivo) -> SIEMPRE RED (No cachar)
    if (url.pathname.includes('/api/buses-activos/')) {
        event.respondWith(fetch(peticion).catch(() => new Response(JSON.stringify({ buses: [] }), { headers: { 'Content-Type': 'application/json' } })));
        return;
    }

    // Estrategia 2: Para los "cuadritos" del Mapa (Tiles de CARTO / OpenStreetMap) -> CACHÉ PRIMERO, LUEGO RED
    if (url.hostname.includes('basemaps.cartocdn.com') || url.hostname.includes('openstreetmap.org')) {
        event.respondWith(
            caches.match(peticion).then(respuestaCache => {
                if (respuestaCache) return respuestaCache; // Si ya vio esta calle antes, la carga sin internet
                
                return fetch(peticion).then(respuestaRed => {
                    // Si hay internet, descarga el mapa y lo guarda silenciosamente para la próxima
                    const respuestaClonada = respuestaRed.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(peticion, respuestaClonada));
                    return respuestaRed;
                }).catch(() => new Response('Error de red')); // Imagen rota silenciosa si no hay mapa guardado
            })
        );
        return;
    }

    // Estrategia 3: Para el resto de la página web -> RED PRIMERO, CACHÉ DE RESPALDO (Offline)
    event.respondWith(
        fetch(peticion).catch(() => {
            return caches.match(peticion).then(respuestaCache => {
                if (respuestaCache) {
                    return respuestaCache;
                }
                // Si está offline y no hay caché, intentamos devolver al menos la raíz '/'
                if (peticion.mode === 'navigate') {
                    return caches.match('/');
                }
            });
        })
    );
});