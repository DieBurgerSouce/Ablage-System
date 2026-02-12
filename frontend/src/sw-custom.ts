/**
 * Custom Service Worker Extensions
 *
 * This file provides custom service worker functionality
 * that extends the Workbox-generated service worker.
 *
 * Features:
 * - Background Sync for offline mutations
 * - Push notifications (future)
 * - Custom cache strategies
 */

/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

// Service Worker debug logging - only in development
// Check for localhost or 127.0.0.1 to determine if in development
const SW_DEBUG = typeof location !== 'undefined' && (
  location.hostname === 'localhost' ||
  location.hostname === '127.0.0.1' ||
  location.hostname.endsWith('.local')
);

const swLog = {
  debug: (message: string, ...args: unknown[]) => {
    if (SW_DEBUG) {
      console.log(`[SW] ${message}`, ...args);
    }
  },
  error: (message: string, ...args: unknown[]) => {
    // Errors always logged (but still prefixed)
    console.error(`[SW] ${message}`, ...args);
  },
};

// Import workbox modules (these are available in the SW context)
import { clientsClaim } from 'workbox-core';
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { NetworkFirst, CacheFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';
import { BackgroundSyncPlugin } from 'workbox-background-sync';

// ============================================
// Basic Setup
// ============================================

// Take control immediately
clientsClaim();

// Clean up old caches
cleanupOutdatedCaches();

// Precache static assets (injected by Workbox at build time)
// @ts-ignore - self.__WB_MANIFEST is injected by workbox
precacheAndRoute(self.__WB_MANIFEST || []);

// ============================================
// Background Sync Queue
// ============================================

// Create a queue for offline mutations
const offlineMutationsQueue = new BackgroundSyncPlugin('offline-mutations', {
  maxRetentionTime: 24 * 60, // Retry for 24 hours
  onSync: async ({ queue }) => {
    let entry;
    while ((entry = await queue.shiftRequest())) {
      try {
        await fetch(entry.request);
        swLog.debug('Background sync successful:', entry.request.url);
      } catch (error) {
        swLog.error('Background sync failed:', entry.request.url, error);
        // Put the request back in the queue
        await queue.unshiftRequest(entry);
        throw error;
      }
    }
    swLog.debug('Queue replay complete');
  },
});

// ============================================
// API Caching with Background Sync
// ============================================

// API routes - NetworkFirst with background sync for mutations
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/v1/'),
  new NetworkFirst({
    cacheName: 'api-cache',
    networkTimeoutSeconds: 10,
    plugins: [
      new CacheableResponsePlugin({
        statuses: [0, 200],
      }),
      new ExpirationPlugin({
        maxEntries: 100,
        maxAgeSeconds: 60 * 60 * 24, // 24 hours
      }),
    ],
  }),
  'GET'
);

// POST/PUT/PATCH/DELETE requests - queue when offline
registerRoute(
  ({ url, request }) =>
    url.pathname.startsWith('/api/v1/') &&
    ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method),
  async ({ request, event }) => {
    try {
      // Try to make the request
      const response = await fetch(request.clone());
      return response;
    } catch (error) {
      // If offline, queue the request
      swLog.debug('Request queued for background sync:', request.url);

      // Clone request and store in queue
      const requestData = {
        url: request.url,
        method: request.method,
        headers: Object.fromEntries(request.headers.entries()),
        body: await request.text(),
      };

      // Store in IndexedDB for our sync service
      await storeOfflineRequest(requestData);

      // Return a synthetic response
      return new Response(
        JSON.stringify({
          success: true,
          queued: true,
          message: 'Anfrage für Hintergrund-Sync gespeichert',
        }),
        {
          status: 202,
          statusText: 'Accepted',
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }
  },
  'POST'
);

// Same for PUT
registerRoute(
  ({ url, request }) =>
    url.pathname.startsWith('/api/v1/') && request.method === 'PUT',
  async ({ request }) => {
    try {
      return await fetch(request.clone());
    } catch (error) {
      const requestData = {
        url: request.url,
        method: request.method,
        headers: Object.fromEntries(request.headers.entries()),
        body: await request.text(),
      };
      await storeOfflineRequest(requestData);
      return new Response(
        JSON.stringify({ success: true, queued: true }),
        { status: 202, headers: { 'Content-Type': 'application/json' } }
      );
    }
  }
);

// Same for PATCH
registerRoute(
  ({ url, request }) =>
    url.pathname.startsWith('/api/v1/') && request.method === 'PATCH',
  async ({ request }) => {
    try {
      return await fetch(request.clone());
    } catch (error) {
      const requestData = {
        url: request.url,
        method: request.method,
        headers: Object.fromEntries(request.headers.entries()),
        body: await request.text(),
      };
      await storeOfflineRequest(requestData);
      return new Response(
        JSON.stringify({ success: true, queued: true }),
        { status: 202, headers: { 'Content-Type': 'application/json' } }
      );
    }
  }
);

// ============================================
// Document/File Caching
// ============================================

registerRoute(
  ({ url }) =>
    url.pathname.includes('/documents/') ||
    url.pathname.includes('/files/') ||
    url.pathname.includes('/storage/'),
  new CacheFirst({
    cacheName: 'documents-cache',
    plugins: [
      new CacheableResponsePlugin({
        statuses: [0, 200],
      }),
      new ExpirationPlugin({
        maxEntries: 50,
        maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
      }),
    ],
  })
);

// ============================================
// Image Caching
// ============================================

registerRoute(
  ({ request }) => request.destination === 'image',
  new CacheFirst({
    cacheName: 'images-cache',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 100,
        maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
      }),
    ],
  })
);

// ============================================
// Font Caching
// ============================================

registerRoute(
  ({ request }) => request.destination === 'font',
  new CacheFirst({
    cacheName: 'fonts-cache',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 20,
        maxAgeSeconds: 60 * 60 * 24 * 365, // 1 year
      }),
    ],
  })
);

// ============================================
// Static Assets
// ============================================

registerRoute(
  ({ request }) =>
    request.destination === 'script' || request.destination === 'style',
  new StaleWhileRevalidate({
    cacheName: 'static-resources',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 50,
        maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
      }),
    ],
  })
);

// ============================================
// Background Sync Event Handler
// ============================================

self.addEventListener('sync', (event: any) => {
  if (event.tag === 'offline-mutations') {
    swLog.debug('Background sync triggered: offline-mutations');
    event.waitUntil(syncOfflineRequests());
  }
});

// ============================================
// IndexedDB Helper Functions
// ============================================

interface OfflineRequest {
  id: string;
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
  timestamp: number;
}

async function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('sw-offline-queue', 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('requests')) {
        const store = db.createObjectStore('requests', { keyPath: 'id' });
        store.createIndex('timestamp', 'timestamp');
      }
    };
  });
}

async function storeOfflineRequest(requestData: Omit<OfflineRequest, 'id' | 'timestamp'>): Promise<void> {
  const db = await openDB();
  const tx = db.transaction('requests', 'readwrite');
  const store = tx.objectStore('requests');

  const fullRequest: OfflineRequest = {
    ...requestData,
    id: crypto.randomUUID(),
    timestamp: Date.now(),
  };

  store.put(fullRequest);

  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function getOfflineRequests(): Promise<OfflineRequest[]> {
  const db = await openDB();
  const tx = db.transaction('requests', 'readonly');
  const store = tx.objectStore('requests');
  const index = store.index('timestamp');

  return new Promise((resolve, reject) => {
    const request = index.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function removeOfflineRequest(id: string): Promise<void> {
  const db = await openDB();
  const tx = db.transaction('requests', 'readwrite');
  const store = tx.objectStore('requests');
  store.delete(id);

  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function syncOfflineRequests(): Promise<void> {
  const requests = await getOfflineRequests();
  swLog.debug(`Syncing ${requests.length} offline requests`);

  for (const req of requests) {
    try {
      const response = await fetch(req.url, {
        method: req.method,
        headers: req.headers,
        body: req.body || undefined,
      });

      if (response.ok) {
        await removeOfflineRequest(req.id);
        swLog.debug('Synced request:', req.url);
      } else {
        swLog.error('Sync failed:', req.url, response.status);
      }
    } catch (error) {
      swLog.error('Sync error:', req.url, error);
      // Leave in queue for next sync
      break; // Stop on first failure to maintain order
    }
  }

  // Notify clients of sync completion
  const clients = await self.clients.matchAll();
  clients.forEach((client) => {
    client.postMessage({
      type: 'SYNC_COMPLETE',
      timestamp: Date.now(),
    });
  });
}

// ============================================
// Web Share Target Handler
// ============================================

// Handle POST requests to /share-target from Web Share Target API
self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url);

  // Handle share-target POST requests
  if (url.pathname === '/share-target' && event.request.method === 'POST') {
    swLog.debug('Handling share-target POST request');

    event.respondWith(
      (async () => {
        try {
          // Clone the request to read the body
          const formData = await event.request.formData();

          // Cache the shared files for the share page to retrieve
          const cache = await caches.open('share-target-cache');

          // Create a new response with the form data
          const response = new Response(formData);
          await cache.put('/share-target-files', response);

          swLog.debug('Shared files cached successfully');

          // Build redirect URL with query params
          const title = formData.get('title');
          const text = formData.get('text');
          const sharedUrl = formData.get('url');

          const redirectParams = new URLSearchParams();
          if (title) redirectParams.set('title', title.toString());
          if (text) redirectParams.set('text', text.toString());
          if (sharedUrl) redirectParams.set('url', sharedUrl.toString());

          const redirectUrl = redirectParams.toString()
            ? `/share?${redirectParams.toString()}`
            : '/share';

          // Redirect to the share page
          return Response.redirect(redirectUrl, 303);
        } catch (error) {
          swLog.error('Share target handling failed:', error);
          // On error, still redirect to share page
          return Response.redirect('/share', 303);
        }
      })()
    );
    return;
  }

  // Handle open-file GET requests (File Handling API redirect)
  if (url.pathname === '/open-file') {
    // Let the route handle it normally - files come via launchQueue API
    return;
  }
});

// ============================================
// Message Handler
// ============================================

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'TRIGGER_SYNC') {
    syncOfflineRequests();
  }
});

// ============================================
// Install Event
// ============================================

self.addEventListener('install', (_event) => {
  swLog.debug('Service Worker installing');
  self.skipWaiting();
});

// ============================================
// Activate Event
// ============================================

self.addEventListener('activate', (event) => {
  swLog.debug('Service Worker activating');
  event.waitUntil(self.clients.claim());
});

export {};
