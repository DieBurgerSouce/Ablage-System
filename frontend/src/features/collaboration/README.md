# Collaboration Features - Quick Reference

React frontend collaboration features for the Ablage-System.

---

## 📦 Installation

All features are already integrated. Import from the collaboration feature:

```tsx
import {
  // Hooks
  useDocumentLock,
  usePresence,
  useDocumentActivityRealtime,
  useMentions,
  // Components
  PresenceIndicator,
  DocumentLockBanner,
  ActivityTimeline,
  MentionsBadge,
} from '@/features/collaboration';
```

---

## 🎯 Quick Start

### 1. Document Lock

```tsx
const { isLocked, lock, isLockedByMe, toggleLock } = useDocumentLock(documentId, userId);

// Show lock banner if locked by someone else
{isLocked && !isLockedByMe && lock && (
  <DocumentLockBanner
    lock={lock}
    currentUserId={userId}
    onForceLock={toggleLock}
  />
)}
```

### 2. Presence Indicator

```tsx
const { viewers } = usePresence(documentId);

<PresenceIndicator
  viewers={viewers}
  currentUserId={userId}
  maxVisible={3}
/>
```

### 3. Activity Timeline

```tsx
const { activities } = useDocumentActivityRealtime(documentId);

<ActivityTimeline
  activities={activities}
  height="500px"
  groupByDate
/>
```

### 4. Mentions Badge

```tsx
<MentionsBadge showPreview />
```

---

## 🔌 Hooks API

### `useDocumentLock(documentId, currentUserId)`

**Returns**:
```ts
{
  isLocked: boolean;
  lock?: DocumentLock;
  isLockedByMe: boolean;
  canEdit: boolean;
  isLoading: boolean;
  toggleLock: () => Promise<void>;
  isToggling: boolean;
  lockError?: Error;
}
```

### `usePresence(documentId, enabled?)`

**Returns**:
```ts
{
  viewers: PresenceUser[];
  viewerCount: number;
  isLoading: boolean;
  error?: Error;
  refetch: () => void;
}
```

### `useDocumentActivityRealtime(documentId)`

**Returns**:
```ts
{
  activities: Activity[];
  total: number;
  hasMore: boolean;
  isLoading: boolean;
  error?: Error;
  refetch: () => void;
}
```

### `useMentions(unreadOnly?)`

**Returns**:
```ts
{
  data: {
    mentions: MentionItem[];
    unread_count: number;
    total: number;
  };
  isLoading: boolean;
  error?: Error;
}
```

### `useUnreadMentionsCount()`

**Returns**: `number` - Count of unread mentions

---

## 🎨 Component Props

### `<PresenceIndicator>`

```tsx
<PresenceIndicator
  viewers={PresenceUser[]}
  currentUserId="user-id"
  maxVisible={3}
  size="sm" | "md"
  showText={true}
/>
```

### `<DocumentLockBanner>`

```tsx
<DocumentLockBanner
  lock={DocumentLock}
  currentUserId="user-id"
  onForceLock={() => void}
  isForcing={false}
  variant="info" | "warning"
/>
```

### `<ActivityTimeline>`

```tsx
<ActivityTimeline
  activities={Activity[]}
  showAvatars={true}
  groupByDate={true}
  height="500px"
  emptyMessage="Keine Aktivitäten"
/>
```

### `<MentionsBadge>`

```tsx
<MentionsBadge
  showPreview={true}
  previewLimit={5}
/>
```

---

## 🌐 Backend Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/collaboration/documents/{id}/lock` | GET | Check lock |
| `/collaboration/documents/{id}/lock` | POST | Lock |
| `/collaboration/documents/{id}/lock` | DELETE | Unlock |
| `/collaboration/documents/{id}/presence` | GET | Viewers |
| `/collaboration/documents/{id}/activity` | GET | Activity |
| `/collaboration/activity/feed` | GET | Feed |
| `/collaboration/mentions` | GET | Mentions |
| `/collaboration/documents/{id}/mentions` | POST | Create |
| `/collaboration/mentions/{id}/read` | PATCH | Mark read |

---

## 🔄 Real-time Updates

All hooks integrate with WebSocket for instant updates:

```tsx
// Automatic invalidation on events
useRealtimeEvent('document.viewed', (event) => {
  // Presence updates automatically
});
```

Polling fallbacks:
- Lock: 10s
- Presence: 5s
- Mentions: 30s

---

## 🧪 Testing

```tsx
import { renderHook, waitFor } from '@testing-library/react';
import { useDocumentLock } from './hooks/useDocumentLock';

test('locks document', async () => {
  const { result } = renderHook(() => useDocumentLock('doc-1', 'user-1'));
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  await result.current.toggleLock();
  expect(result.current.isLockedByMe).toBe(true);
});
```

---

## 📝 TypeScript Types

```ts
interface DocumentLock {
  document_id: string;
  locked_by_user_id: string;
  locked_by_user_name: string;
  locked_at: string;
  expires_at?: string;
}

interface PresenceUser {
  user_id: string;
  user_name: string;
  user_email?: string;
  user_avatar?: string;
  joined_at: string;
}

interface Activity {
  id: string;
  documentId: string;
  userId: string;
  userName: string;
  userAvatar?: string;
  type: ActivityType;
  description: string;
  metadata?: Record<string, unknown>;
  createdAt: string;
}

interface MentionItem {
  id: string;
  document_id: string;
  document_name: string;
  comment_id: string;
  comment_text: string;
  mentioned_by_user_id: string;
  mentioned_by_user_name: string;
  mentioned_at: string;
  is_read: boolean;
}
```

---

## ✅ Features

- ✅ Document locking with force-lock
- ✅ Real-time presence tracking
- ✅ Activity timeline with grouping
- ✅ @mention notifications
- ✅ WebSocket integration
- ✅ Polling fallbacks
- ✅ German localization
- ✅ TypeScript types
- ✅ TanStack Query caching
- ✅ Success/error toasts

---

## 📚 Examples

See `examples/DocumentViewerIntegration.example.tsx` for complete integration examples.

---

## 🐛 Troubleshooting

### Lock not releasing
- Check backend expires_at implementation
- Verify DELETE endpoint returns 200

### Presence not updating
- Verify WebSocket connection is active
- Check presence endpoint returns correct users

### Mentions not showing
- Verify POST /mentions endpoint works
- Check unread_count in response

---

## 📖 Full Documentation

See `/docs/collaboration-frontend-implementation.md` for complete documentation.
