/**
 * Ablage-System Service Worker
 *
 * Features:
 * - Offline caching (App Shell + Dynamic Content)
 * - Background sync for queued uploads
 * - Push notifications handling
 * - Cache-first strategy for static assets
 * - Network-first for API calls with fallback
 *
 * Phase 3.1 der Feature-Roadmap (Januar 2026)
 */

const CACHE_VERSION = 'v1.0.0';
const STATIC_CACHE = `ablage-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `ablage-dynamic-${CACHE_VERSION}`;
const API_CACHE = `ablage-api-${CACHE_VERSION}`;
const IMAGE_CACHE = `ablage-images-${CACHE_VERSION}`;

// ==================== Cache Configuration ====================

// Static assets to cache immediately on install
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/offline.html',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png',
];

// API endpoints to cache (with network-first strategy)
const CACHEABLE_API_PATTERNS = [
  /\/api\/v1\/companies$/,
  /\/api\/v1\/document-types$/,
  /\/api\/v1\/categories$/,
  /\/api\/v1\/users\/me$/,
];

// URLs that should never be cached
const NEVER_CACHE_PATTERNS = [
  /\/api\/v1\/auth\//,
  /\/api\/v1\/uploads\//,
  /\/api\/v1\/ws\//,
];

// Maximum cache sizes
const CACHE_LIMITS = {
  dynamic: 100,
  api: 50,
  images: 100,
};

// ==================== Install Event ====================

self.addEventListener('install', (event) => {
  console.log('[ServiceWorker] Installing...');

  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[ServiceWorker] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('[ServiceWorker] Static assets cached');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[ServiceWorker] Install failed:', error);
      })
  );
});

// ==================== Activate Event ====================

self.addEventListener('activate', (event) => {
  console.log('[ServiceWorker] Activating...');

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => {
              // Delete old caches
              return cacheName.startsWith('ablage-') &&
                     !cacheName.includes(CACHE_VERSION);
            })
            .map((cacheName) => {
              console.log('[ServiceWorker] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            })
        );
      })
      .then(() => {
        console.log('[ServiceWorker] Claiming clients');
        return self.clients.claim();
      })
  );
});

// ==================== Fetch Event ====================

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip requests that should never be cached
  if (NEVER_CACHE_PATTERNS.some((pattern) => pattern.test(url.pathname))) {
    return;
  }

  // Handle different request types
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(handleApiRequest(request));
  } else if (isImageRequest(request)) {
    event.respondWith(handleImageRequest(request));
  } else if (isStaticAsset(request)) {
    event.respondWith(handleStaticRequest(request));
  } else {
    event.respondWith(handleNavigationRequest(request));
  }
});

// ==================== Request Handlers ====================

/**
 * API Request Handler - Network-first with cache fallback
 */
async function handleApiRequest(request) {
  const url = new URL(request.url);
  const isCacheable = CACHEABLE_API_PATTERNS.some((pattern) => pattern.test(url.pathname));

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok && isCacheable) {
      const cache = await caches.open(API_CACHE);
      cache.put(request, networkResponse.clone());
      await trimCache(API_CACHE, CACHE_LIMITS.api);
    }

    return networkResponse;
  } catch (error) {
    console.log('[ServiceWorker] Network failed, trying cache for:', request.url);

    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Return offline response for API errors
    return new Response(
      JSON.stringify({
        error: 'Offline',
        message: 'Sie sind offline. Diese Daten sind nicht verfuegbar.'
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }
    );
  }
}

/**
 * Image Request Handler - Cache-first with network fallback
 */
async function handleImageRequest(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(IMAGE_CACHE);
      cache.put(request, networkResponse.clone());
      await trimCache(IMAGE_CACHE, CACHE_LIMITS.images);
    }

    return networkResponse;
  } catch (error) {
    // Return placeholder image for offline
    return caches.match('/icons/placeholder-image.png');
  }
}

/**
 * Static Asset Handler - Cache-first
 */
async function handleStaticRequest(request) {
  const cachedResponse = await caches.match(request);
  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
      await trimCache(DYNAMIC_CACHE, CACHE_LIMITS.dynamic);
    }

    return networkResponse;
  } catch (error) {
    console.error('[ServiceWorker] Static fetch failed:', error);
    throw error;
  }
}

/**
 * Navigation Request Handler - Network-first with offline fallback
 */
async function handleNavigationRequest(request) {
  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.log('[ServiceWorker] Navigation offline, serving shell');

    // Try to serve cached page
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Serve offline page
    return caches.match('/offline.html');
  }
}

// ==================== Utility Functions ====================

function isImageRequest(request) {
  const url = new URL(request.url);
  return /\.(jpg|jpeg|png|gif|webp|svg|ico)$/i.test(url.pathname) ||
         request.destination === 'image';
}

function isStaticAsset(request) {
  const url = new URL(request.url);
  return /\.(js|css|woff|woff2|ttf|eot)$/i.test(url.pathname) ||
         ['script', 'style', 'font'].includes(request.destination);
}

async function trimCache(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();

  if (keys.length > maxItems) {
    const keysToDelete = keys.slice(0, keys.length - maxItems);
    await Promise.all(keysToDelete.map((key) => cache.delete(key)));
  }
}

// ==================== Background Sync ====================

self.addEventListener('sync', (event) => {
  console.log('[ServiceWorker] Sync event:', event.tag);

  if (event.tag === 'upload-documents') {
    event.waitUntil(syncQueuedUploads());
  }

  if (event.tag === 'sync-offline-changes') {
    event.waitUntil(syncOfflineChanges());
  }
});

async function syncQueuedUploads() {
  console.log('[ServiceWorker] Syncing queued uploads...');

  try {
    // Get queued uploads from IndexedDB
    const db = await openDatabase();
    const uploads = await getAllUploads(db);

    for (const upload of uploads) {
      try {
        const formData = new FormData();
        formData.append('file', upload.file);
        if (upload.metadata) {
          formData.append('metadata', JSON.stringify(upload.metadata));
        }

        const response = await fetch('/api/v1/documents/upload', {
          method: 'POST',
          body: formData,
          credentials: 'include',
        });

        if (response.ok) {
          await deleteUpload(db, upload.id);
          console.log('[ServiceWorker] Upload synced:', upload.id);
        }
      } catch (error) {
        console.error('[ServiceWorker] Upload sync failed:', error);
      }
    }
  } catch (error) {
    console.error('[ServiceWorker] Sync queued uploads failed:', error);
  }
}

async function syncOfflineChanges() {
  console.log('[ServiceWorker] Syncing offline changes...');
  // Implement offline changes sync if needed
}

// ==================== IndexedDB Helpers ====================

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('ablage-offline', 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      if (!db.objectStoreNames.contains('uploads')) {
        db.createObjectStore('uploads', { keyPath: 'id', autoIncrement: true });
      }

      if (!db.objectStoreNames.contains('offline-changes')) {
        db.createObjectStore('offline-changes', { keyPath: 'id', autoIncrement: true });
      }
    };
  });
}

function getAllUploads(db) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['uploads'], 'readonly');
    const store = transaction.objectStore('uploads');
    const request = store.getAll();

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}

function deleteUpload(db, id) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['uploads'], 'readwrite');
    const store = transaction.objectStore('uploads');
    const request = store.delete(id);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

// ==================== Push Notifications ====================

/**
 * Notification Type to URL Mapping for Deep Linking
 */
const NOTIFICATION_ROUTES = {
  'document': '/documents',
  'document_processed': '/documents',
  'approval_required': '/approvals',
  'workflow_completed': '/workflows',
  'system_alert': '/alerts',
  'payment_reminder': '/invoices',
  'error_notification': '/alerts',
  'deadline': '/deadlines',
  'skonto': '/banking/skonto',
  'shipment': '/shipments',
};

/**
 * Get deep link URL based on notification type and data
 */
function getNotificationUrl(notificationData) {
  const type = notificationData.type || 'default';
  const baseUrl = NOTIFICATION_ROUTES[type] || '/';

  // Build URL with optional document/entity ID
  if (notificationData.documentId) {
    return `${baseUrl}/${notificationData.documentId}`;
  }
  if (notificationData.entityId) {
    return `${baseUrl}?entity=${notificationData.entityId}`;
  }
  if (notificationData.url) {
    return notificationData.url;
  }

  return baseUrl;
}

self.addEventListener('push', (event) => {
  console.log('[ServiceWorker] Push received');

  let data = {
    title: 'Ablage-System',
    body: 'Neue Benachrichtigung',
    icon: '/icons/icon-192x192.png',
    badge: '/icons/icon-72x72.png',
    tag: 'default',
    data: {},
  };

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (error) {
      console.error('[ServiceWorker] Push parse error:', error);
    }
  }

  // Determine URL for deep linking
  const notificationUrl = getNotificationUrl(data.data);

  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    tag: data.tag,
    data: {
      ...data.data,
      url: notificationUrl,
      timestamp: Date.now(),
    },
    actions: data.actions || [],
    vibrate: [200, 100, 200],
    requireInteraction: data.priority === 'high' || data.requireInteraction,
    silent: data.silent || false,
  };

  // Add image if provided
  if (data.image) {
    options.image = data.image;
  }

  // Add renotify for tag updates
  if (data.tag && data.tag !== 'default') {
    options.renotify = true;
  }

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  console.log('[ServiceWorker] Notification clicked:', event.notification.tag);

  event.notification.close();

  const notificationData = event.notification.data || {};
  let urlToOpen = notificationData.url || '/';

  // Handle action button clicks
  if (event.action) {
    console.log('[ServiceWorker] Action clicked:', event.action);

    // Route based on action
    switch (event.action) {
      case 'approve':
        urlToOpen = `/approvals/${notificationData.documentId}?action=approve`;
        break;
      case 'reject':
        urlToOpen = `/approvals/${notificationData.documentId}?action=reject`;
        break;
      case 'view':
        urlToOpen = notificationData.url || '/';
        break;
      case 'dismiss':
        return; // Just close the notification
      default:
        // Use default URL
        break;
    }
  }

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((windowClients) => {
        // Check if there's already a window open
        for (const client of windowClients) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            // Focus existing window and navigate
            return client.focus().then(() => {
              // Post message to handle navigation in the app
              client.postMessage({
                type: 'NOTIFICATION_CLICK',
                url: urlToOpen,
                data: notificationData,
              });
              return client;
            });
          }
        }
        // Open new window
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Handle notification close (for analytics)
self.addEventListener('notificationclose', (event) => {
  const notificationData = event.notification.data || {};
  console.log('[ServiceWorker] Notification closed:', event.notification.tag, {
    dismissed: true,
    timestamp: Date.now(),
    notificationId: notificationData.notificationId,
  });
});

// ==================== Periodic Background Fetch ====================

self.addEventListener('periodicsync', (event) => {
  console.log('[ServiceWorker] Periodic sync:', event.tag);

  if (event.tag === 'sync-documents') {
    event.waitUntil(syncDocumentMetadata());
  }

  if (event.tag === 'check-notifications') {
    event.waitUntil(checkPendingNotifications());
  }
});

async function syncDocumentMetadata() {
  console.log('[ServiceWorker] Syncing document metadata...');

  try {
    // Fetch recent document metadata for offline access
    const response = await fetch('/api/v1/documents/recent?limit=50', {
      credentials: 'include',
    });

    if (response.ok) {
      const cache = await caches.open(API_CACHE);
      await cache.put(
        new Request('/api/v1/documents/recent?limit=50'),
        response.clone()
      );
      console.log('[ServiceWorker] Document metadata synced');
    }
  } catch (error) {
    console.error('[ServiceWorker] Document sync failed:', error);
  }
}

async function checkPendingNotifications() {
  console.log('[ServiceWorker] Checking pending notifications...');

  try {
    const response = await fetch('/api/v1/notifications/pending', {
      credentials: 'include',
    });

    if (response.ok) {
      const data = await response.json();

      // Show notification for pending items
      if (data.count > 0) {
        await self.registration.showNotification('Ausstehende Aufgaben', {
          body: `Sie haben ${data.count} ausstehende ${data.count === 1 ? 'Aufgabe' : 'Aufgaben'}`,
          icon: '/icons/icon-192x192.png',
          badge: '/icons/icon-72x72.png',
          tag: 'pending-tasks',
          data: { type: 'pending_tasks', url: '/tasks' },
        });
      }
    }
  } catch (error) {
    console.error('[ServiceWorker] Notification check failed:', error);
  }
}

// ==================== Message Handler ====================

self.addEventListener('message', (event) => {
  console.log('[ServiceWorker] Message received:', event.data);

  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(DYNAMIC_CACHE)
        .then((cache) => cache.addAll(event.data.urls))
    );
  }

  if (event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys()
        .then((cacheNames) => Promise.all(
          cacheNames
            .filter((name) => name.startsWith('ablage-'))
            .map((name) => caches.delete(name))
        ))
    );
  }

  if (event.data.type === 'CACHE_DOCUMENT') {
    // Cache a specific document for offline access
    event.waitUntil(
      caches.open(DYNAMIC_CACHE)
        .then((cache) => {
          const { documentId, url, content } = event.data;
          if (url && content) {
            const response = new Response(JSON.stringify(content), {
              headers: { 'Content-Type': 'application/json' },
            });
            return cache.put(url, response);
          }
        })
    );
  }

  if (event.data.type === 'REGISTER_PERIODIC_SYNC') {
    // Register periodic background sync
    event.waitUntil(
      self.registration.periodicSync?.register(event.data.tag, {
        minInterval: event.data.minInterval || 24 * 60 * 60 * 1000, // Default 24 hours
      }).catch((error) => {
        console.log('[ServiceWorker] Periodic sync not available:', error);
      })
    );
  }

  if (event.data.type === 'GET_CACHED_DOCUMENTS') {
    // Return list of cached documents
    event.waitUntil(
      caches.open(DYNAMIC_CACHE)
        .then((cache) => cache.keys())
        .then((keys) => {
          const documentUrls = keys
            .filter((request) => request.url.includes('/documents/'))
            .map((request) => request.url);

          event.ports[0]?.postMessage({ documentUrls });
        })
    );
  }
});

console.log('[ServiceWorker] Script loaded v1.1.0 (Phase 8 - PWA Mobile Foundation)');
