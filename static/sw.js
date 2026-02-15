// Service Worker for offline functionality
const CACHE_NAME = 'aid-tracking-v1';
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/js/main.js',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

// Install Service Worker
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                return cache.addAll(urlsToCache);
            })
    );
});

// Fetch event handler
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Return cached version or fetch new
                return response || fetch(event.request)
                    .then(response => {
                        // Cache new responses for future offline use
                        if (response.status === 200) {
                            const responseClone = response.clone();
                            caches.open(CACHE_NAME)
                                .then(cache => {
                                    cache.put(event.request, responseClone);
                                });
                        }
                        return response;
                    });
            })
            .catch(() => {
                // Return offline page if no cached version exists
                if (event.request.mode === 'navigate') {
                    return caches.match('/offline.html');
                }
            })
    );
});

// Background sync for offline submissions
self.addEventListener('sync', event => {
    if (event.tag === 'sync-aid-requests') {
        event.waitUntil(syncAidRequests());
    }
});

// Function to sync stored offline submissions
async function syncAidRequests() {
    try {
        const db = await openDB();
        const offlineRequests = await db.getAll('offlineRequests');
        
        for (const request of offlineRequests) {
            await fetch('/request_aid', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(request)
            });
            
            await db.delete('offlineRequests', request.id);
        }
    } catch (error) {
        console.error('Error syncing offline requests:', error);
    }
}