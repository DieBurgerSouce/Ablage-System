/**
 * Notification Center - Type Definitions
 *
 * TypeScript Interfaces für Benachrichtigungen und Einstellungen
 */

/**
 * Prioritätsstufen für Benachrichtigungen
 */
export enum NotificationPriority {
  CRITICAL = 'critical',
  WARNING = 'warning',
  INFO = 'info'
}

/**
 * Benachrichtigungstypen
 */
export enum NotificationType {
  SYSTEM = 'system',
  DOCUMENT = 'document',
  INVOICE = 'invoice',
  WORKFLOW = 'workflow',
  ALERT = 'alert'
}

/**
 * Benachrichtigungs-Metadaten
 *
 * SECURITY NOTE: Additional metadata fields are restricted to primitive types
 * and arrays of primitives to prevent prototype pollution attacks.
 * Complex nested objects should use the explicitly typed fields above.
 */
export interface NotificationMetadata {
  // Explicitly typed known fields
  document_id?: string;
  invoice_id?: string;
  entity_id?: string;
  workflow_id?: string;
  action_url?: string;
  // Bounded additional fields (no complex nested objects)
  [key: string]: string | number | boolean | null | undefined | string[];
}

/**
 * Benachrichtigungs-Interface
 */
export interface Notification {
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

/**
 * Benachrichtigungs-Einstellungen
 */
export interface NotificationSettings {
  id: string;
  user_id: string;
  email_enabled: boolean;
  push_enabled: boolean;
  priorities: NotificationPriority[];
  types: NotificationType[];
  created_at: string;
  updated_at: string;
}

/**
 * API Response für Benachrichtigungsliste
 */
export interface NotificationsResponse {
  items: Notification[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

/**
 * API Response für Unread Count
 */
export interface UnreadCountResponse {
  count: number;
}

/**
 * Filter für Benachrichtigungen
 */
export interface NotificationFilter {
  priority?: NotificationPriority;
  type?: NotificationType;
  unread_only?: boolean;
}

/**
 * Update-Payload für Einstellungen
 */
export interface NotificationSettingsUpdate {
  email_enabled?: boolean;
  push_enabled?: boolean;
  priorities?: NotificationPriority[];
  types?: NotificationType[];
}

/**
 * Bulk-Dismiss Payload
 */
export interface BulkDismissPayload {
  notification_ids: string[];
}
