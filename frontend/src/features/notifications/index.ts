/**
 * Notification Center - Public API
 *
 * Re-exports für externe Nutzung
 */

// Components
export { NotificationCenter } from './components/NotificationCenter';
export { NotificationBell } from './components/NotificationBell';
export { NotificationItem } from './components/NotificationItem';
export { NotificationSettings } from './components/NotificationSettings';

// Hooks
export {
  useNotifications,
  useNotification,
  useUnreadCount,
  useMarkAsRead,
  useMarkAllAsRead,
  useDeleteNotification,
  useBulkDismiss,
  useNotificationSettings,
  useUpdateSettings,
  notificationKeys
} from './hooks/useNotifications';

// API
export {
  getNotifications,
  getNotificationById,
  markAsRead,
  markAllAsRead,
  deleteNotification,
  bulkDismiss,
  getUnreadCount,
  getSettings,
  updateSettings
} from './api';

// Types
export type {
  Notification,
  NotificationSettings as NotificationSettingsData,
  NotificationSettingsUpdate,
  NotificationsResponse,
  UnreadCountResponse,
  NotificationFilter,
  NotificationMetadata,
  BulkDismissPayload
} from './types';

export { NotificationPriority, NotificationType } from './types';
