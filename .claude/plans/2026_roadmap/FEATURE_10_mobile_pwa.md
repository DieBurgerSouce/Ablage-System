# Feature 10: Mobile PWA

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P3 - Nice-to-Have
> **Geschaetzter Aufwand**: 2-3 Wochen
> **Abhaengigkeiten**: Feature 03 (Notifications)

---

## Executive Summary

Die Mobile PWA (Progressive Web App) ermoeglicht mobilen Zugriff auf das Ablage-System. Foto-Upload direkt vom Handy, Push-Notifications, und Offline-Faehigkeit machen das System auch unterwegs nutzbar. Eine native App ist nicht geplant - die PWA deckt alle Anforderungen ab.

**Business Value:**
- Belege unterwegs fotografieren
- Push-Benachrichtigungen aufs Handy
- Dokumente schnell einsehen
- Keine App-Store Installation noetig

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Foto-Upload | MUSS | Kamera → direkt hochladen |
| FR-02 | Quick-View Dokumente | MUSS | PDF/Images anzeigen |
| FR-03 | Validierung unterwegs | SOLL | Review-Queue abarbeiten |
| FR-04 | Push Notifications | SOLL | Erinnerungen aufs Handy |
| FR-05 | Dashboard-Widgets | SOLL | KPIs mobil |
| FR-06 | Suche | MUSS | Dokumente finden |
| FR-07 | Offline-Cache | SOLL | Zuletzt angesehene Docs |
| FR-08 | Install-Prompt | SOLL | "Zum Homescreen hinzufuegen" |

---

## PWA-Konfiguration

### manifest.json

```json
{
  "name": "Ablage-System",
  "short_name": "Ablage",
  "description": "Intelligente Dokumentenverwaltung",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#1a1a1a",
  "theme_color": "#2196F3",
  "orientation": "portrait-primary",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ],
  "screenshots": [
    {
      "src": "/screenshots/home.png",
      "sizes": "1080x1920",
      "type": "image/png",
      "form_factor": "narrow",
      "label": "Homescreen"
    }
  ],
  "categories": ["business", "productivity"],
  "lang": "de-DE"
}
```

### Service Worker Strategy

```typescript
// frontend/src/service-worker.ts

import { precacheAndRoute } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';

// Precache App Shell
precacheAndRoute(self.__WB_MANIFEST);

// API Requests: Network First
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/'),
  new NetworkFirst({
    cacheName: 'api-cache',
    networkTimeoutSeconds: 10,
    plugins: [
      new ExpirationPlugin({
        maxEntries: 100,
        maxAgeSeconds: 60 * 60,  // 1 hour
      }),
    ],
  })
);

// Document Previews: Cache First
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/v1/documents/') && url.pathname.includes('/preview'),
  new CacheFirst({
    cacheName: 'document-previews',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 50,
        maxAgeSeconds: 7 * 24 * 60 * 60,  // 1 week
      }),
    ],
  })
);

// Static Assets: Stale While Revalidate
registerRoute(
  ({ request }) => request.destination === 'image' ||
                   request.destination === 'script' ||
                   request.destination === 'style',
  new StaleWhileRevalidate({
    cacheName: 'static-assets',
  })
);

// Push Notifications
self.addEventListener('push', (event) => {
  const data = event.data?.json() ?? {};
  const options = {
    body: data.message,
    icon: '/icons/icon-192.png',
    badge: '/icons/badge.png',
    data: { url: data.url },
    actions: data.actions ?? [],
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Notification Click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});
```

---

## Mobile-optimierte Komponenten

### Foto-Upload Component

```typescript
// frontend/src/features/mobile/components/PhotoCapture.tsx

import { useRef, useState } from 'react';
import { Camera, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useUploadDocument } from '@/features/documents/api/documents-api';

export function PhotoCapture() {
  const [preview, setPreview] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useUploadDocument();

  const handleCapture = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setPreview(URL.createObjectURL(file));
    }
  };

  const handleUpload = async () => {
    const file = inputRef.current?.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      await uploadMutation.mutateAsync({
        file,
        source: 'mobile_camera',
        auto_process: true,
      });
      setPreview(null);
      if (inputRef.current) inputRef.current.value = '';
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-4 p-4">
      {preview ? (
        <div className="relative">
          <img
            src={preview}
            alt="Preview"
            className="max-w-full max-h-[50vh] rounded-lg"
          />
          <Button
            variant="destructive"
            size="icon"
            className="absolute top-2 right-2"
            onClick={() => setPreview(null)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <div
          className="w-full aspect-[3/4] bg-muted rounded-lg flex items-center justify-center cursor-pointer"
          onClick={() => inputRef.current?.click()}
        >
          <Camera className="h-16 w-16 text-muted-foreground" />
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleCapture}
      />

      <div className="flex gap-2 w-full">
        <Button
          variant="outline"
          className="flex-1"
          onClick={() => inputRef.current?.click()}
        >
          <Camera className="h-4 w-4 mr-2" />
          Foto aufnehmen
        </Button>

        {preview && (
          <Button
            className="flex-1"
            onClick={handleUpload}
            disabled={isUploading}
          >
            <Upload className="h-4 w-4 mr-2" />
            {isUploading ? 'Wird hochgeladen...' : 'Hochladen'}
          </Button>
        )}
      </div>
    </div>
  );
}
```

### Mobile Navigation

```typescript
// frontend/src/features/mobile/components/MobileNav.tsx

import { Home, Camera, FileText, Bell, Search } from 'lucide-react';
import { Link, useLocation } from '@tanstack/react-router';
import { useNotificationCount } from '@/features/notifications/api/notifications-api';

const navItems = [
  { icon: Home, label: 'Home', path: '/' },
  { icon: Camera, label: 'Foto', path: '/mobile/capture' },
  { icon: FileText, label: 'Dokumente', path: '/documents' },
  { icon: Bell, label: 'Alerts', path: '/notifications', badge: true },
  { icon: Search, label: 'Suche', path: '/search' },
];

export function MobileNav() {
  const location = useLocation();
  const { data: notifCount } = useNotificationCount();

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-background border-t safe-area-pb">
      <div className="flex justify-around items-center h-16">
        {navItems.map(({ icon: Icon, label, path, badge }) => {
          const isActive = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              className={`flex flex-col items-center gap-1 p-2 relative ${
                isActive ? 'text-primary' : 'text-muted-foreground'
              }`}
            >
              <Icon className="h-5 w-5" />
              <span className="text-xs">{label}</span>
              {badge && notifCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground text-xs rounded-full h-5 w-5 flex items-center justify-center">
                  {notifCount > 99 ? '99+' : notifCount}
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
```

---

## Implementation Tasks

### Phase 1: PWA Setup (0.5 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 1.1 | [ ] manifest.json | Vollstaendig konfiguriert |
| 1.2 | [ ] Service Worker | Workbox integriert |
| 1.3 | [ ] Install Prompt | "Zum Homescreen" Prompt |
| 1.4 | [ ] Icons | Alle Groessen generiert |

### Phase 2: Mobile UI (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 2.1 | [ ] Mobile Navigation | Bottom Nav Bar |
| 2.2 | [ ] Foto-Capture | Kamera → Upload |
| 2.3 | [ ] Document Viewer | Touch-optimiert |
| 2.4 | [ ] Mobile Dashboard | KPI Widgets |
| 2.5 | [ ] Responsive Anpassungen | Alle Seiten mobil |

### Phase 3: Push & Offline (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 3.1 | [ ] Push Registration | Subscription gespeichert |
| 3.2 | [ ] Push Backend | Web Push API |
| 3.3 | [ ] Offline Cache | Zuletzt gesehen gecached |
| 3.4 | [ ] Offline Indicator | Banner bei Offline |
| 3.5 | [ ] Sync Queue | Upload bei Reconnect |

### Phase 4: Testing (0.5 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 4.1 | [ ] iOS Safari | PWA funktioniert |
| 4.2 | [ ] Android Chrome | PWA funktioniert |
| 4.3 | [ ] Lighthouse Audit | Score >90 |
| 4.4 | [ ] Touch Gestures | Swipe etc. |

---

## Quality Gates

- [ ] PWA installierbar (iOS + Android)
- [ ] Foto-Upload funktioniert
- [ ] Push Notifications ankommen
- [ ] Offline-Cache funktioniert
- [ ] Alle 4 Display-Modi
- [ ] Touch-optimierte UI
- [ ] Lighthouse Score >90
