// service-worker.js

const CACHE_NAME = 'uni-sync-cache-v1';
const urlsToCache = [
    '/',
    '/index.html',
    '/static/css/styles.css',
    '/static/js/main.js',
    '/manifest.json',
    '/static/icons/icon.png',
    '/static/icons/icon.png'
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                return cache.addAll(urlsToCache);
            })
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                if (response) {
                    return response;  // return cached response if available
                }
                return fetch(event.request);  // else fetch from network
            })
    );
});

self.addEventListener('activate', event => {
    const cacheWhitelist = [CACHE_NAME];
    event.waitUntil(
        caches.keys().then(keyList =>
            Promise.all(keyList.map(key => {
                if (!cacheWhitelist.includes(key)) {
                    return caches.delete(key);
                }
            }))
        )
    );
});
