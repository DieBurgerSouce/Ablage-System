# Notification Center

Vollständiges Benachrichtigungssystem für das Ablage-System mit Bell-Icon, Notification-Center und Einstellungen.

## Features

- ✅ Bell-Icon mit Badge und Unread-Count
- ✅ Notification Center (Sheet/Sidebar)
- ✅ Filter nach Priorität (Alle, Kritisch, Warnungen, Info)
- ✅ Infinite Scroll mit Pagination
- ✅ Swipe-to-dismiss auf Mobile
- ✅ Mark as read / Mark all as read
- ✅ Bulk-Dismiss mit Auswahl
- ✅ Relative Zeit-Anzeige
- ✅ Click-to-navigate mit Link-Unterstützung
- ✅ Einstellungsseite für Kanäle und Filter
- ✅ Optimistic Updates mit TanStack Query
- ✅ Animation bei neuen Benachrichtigungen
- ✅ Vollständig auf Deutsch

## Installation

### 1. Komponenten importieren

```tsx
import { NotificationBell } from '@/features/notifications';
```

### 2. In Header einbinden

```tsx
// In deinem Header/Navbar
<div className="flex items-center gap-2">
  <NotificationBell />
  <UserMenu />
</div>
```

### 3. Einstellungsseite erstellen (optional)

```tsx
// In deiner Route-Datei
import { NotificationSettings } from '@/features/notifications';

function NotificationSettingsPage() {
  return (
    <div className="container max-w-2xl py-8">
      <h1 className="text-2xl font-bold mb-6">Benachrichtigungseinstellungen</h1>
      <NotificationSettings />
    </div>
  );
}
```

## API-Endpunkte

Das Frontend erwartet folgende Backend-Endpunkte:

### Benachrichtigungen

- `GET /api/v1/notifications` - Liste mit Pagination
  - Query-Parameter: `page`, `page_size`, `priority`, `type`, `unread_only`
- `GET /api/v1/notifications/{id}` - Einzelne Benachrichtigung
- `PATCH /api/v1/notifications/{id}/read` - Als gelesen markieren
- `POST /api/v1/notifications/mark-all-read` - Alle als gelesen
- `DELETE /api/v1/notifications/{id}` - Löschen
- `POST /api/v1/notifications/bulk-dismiss` - Mehrere löschen
- `GET /api/v1/notifications/unread-count` - Ungelesen-Anzahl

### Einstellungen

- `GET /api/v1/notifications/settings` - Einstellungen abrufen
- `PATCH /api/v1/notifications/settings` - Einstellungen aktualisieren

## Nutzung der Hooks

### Benachrichtigungen auflisten

```tsx
import { useNotifications } from '@/features/notifications';

function MyComponent() {
  const { data, isLoading, fetchNextPage, hasNextPage } = useNotifications();

  const notifications = data?.pages.flatMap(page => page.items) ?? [];

  return (
    <div>
      {notifications.map(notification => (
        <NotificationItem key={notification.id} notification={notification} />
      ))}
    </div>
  );
}
```

### Mit Filter

```tsx
import { useNotifications, NotificationPriority } from '@/features/notifications';

function CriticalNotifications() {
  const { data } = useNotifications({ priority: NotificationPriority.CRITICAL });
  // ...
}
```

### Unread Count anzeigen

```tsx
import { useUnreadCount } from '@/features/notifications';

function MyBadge() {
  const { data: count } = useUnreadCount();
  return <Badge>{count}</Badge>;
}
```

### Als gelesen markieren

```tsx
import { useMarkAsRead } from '@/features/notifications';

function MyNotification({ id }) {
  const markAsRead = useMarkAsRead();

  const handleClick = () => {
    markAsRead.mutate(id);
  };

  return <button onClick={handleClick}>Als gelesen markieren</button>;
}
```

## Typen

### Notification

```typescript
interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  priority: NotificationPriority;
  read: boolean;
  created_at: string;
  link?: string;
  metadata?: NotificationMetadata;
}
```

### NotificationPriority

```typescript
enum NotificationPriority {
  CRITICAL = 'critical',
  WARNING = 'warning',
  INFO = 'info'
}
```

### NotificationType

```typescript
enum NotificationType {
  SYSTEM = 'system',
  DOCUMENT = 'document',
  INVOICE = 'invoice',
  WORKFLOW = 'workflow',
  ALERT = 'alert'
}
```

## Styling & Themes

Das Notification Center nutzt shadcn/ui Komponenten und passt sich automatisch an Dark/Light Mode an.

### Anpassungen

Icons können in `NotificationItem.tsx` angepasst werden:

```tsx
// In getIcon() Funktion
switch (notification.type) {
  case NotificationType.DOCUMENT:
    return <FileText className="h-5 w-5 text-blue-500" />;
  // ...
}
```

## Performance

- **Optimistic Updates**: Änderungen werden sofort im UI reflektiert
- **Caching**: TanStack Query cached Daten für 1 Minute
- **Infinite Scroll**: Lazy Loading mit automatischem Nachladen
- **Debouncing**: Swipe-to-dismiss mit 100px Threshold

## Accessibility

- ✅ Keyboard-Navigation
- ✅ ARIA-Labels auf Bell-Icon
- ✅ Screen-Reader optimiert
- ✅ Focus-Management im Sheet

## Mobile Support

- ✅ Swipe-to-dismiss Geste
- ✅ Touch-optimierte Tap-Bereiche
- ✅ Responsive Design
- ✅ Native-feeling Animations

## Troubleshooting

### Bell-Icon zeigt keine Badge

- Prüfe ob `useUnreadCount()` Daten empfängt
- Backend-Endpunkt `/api/v1/notifications/unread-count` muss erreichbar sein

### Notifications laden nicht

- Prüfe Network-Tab für API-Fehler
- Authentifizierung korrekt? (JWT-Token)
- CORS-Einstellungen im Backend korrekt?

### Optimistic Updates funktionieren nicht

- TanStack Query Cache könnte deaktiviert sein
- Prüfe `queryClient` Konfiguration in `main.tsx`

## Backend-Integration

Beispiel-Response für `GET /api/v1/notifications`:

```json
{
  "items": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "type": "document",
      "title": "Dokument verarbeitet",
      "message": "Rechnung_2024_001.pdf wurde erfolgreich verarbeitet",
      "priority": "info",
      "read": false,
      "created_at": "2024-01-19T10:30:00Z",
      "link": "/documents/123e4567-e89b-12d3-a456-426614174000",
      "metadata": {
        "document_id": "123e4567-e89b-12d3-a456-426614174000"
      }
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "has_more": true
}
```

## Weitere Informationen

- [TanStack Query Docs](https://tanstack.com/query/latest)
- [shadcn/ui Docs](https://ui.shadcn.com)
- [Backend API Spezifikation](../../../../.claude/Docs/API/API_Documentation.md)
