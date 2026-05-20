/**
 * Kalender-Synchronisation Typen
 *
 * Typdefinitionen für die Kalender-Sync-Funktionalität
 * inkl. OAuth, Sync-Status, Event-Vorschau und Konfiguration.
 */

export type CalendarProviderType = 'google' | 'outlook' | 'caldav' | 'ical_file';

export interface OAuthStatus {
  connected: boolean;
  email: string | null;
  expires_at: string | null;
  provider: CalendarProviderType;
}

export interface OAuthStatusMap {
  google: OAuthStatus;
  outlook: OAuthStatus;
}

export interface OAuthAuthorizeRequest {
  provider: CalendarProviderType;
  client_id: string;
  client_secret: string;
  redirect_uri: string;
}

export interface OAuthAuthorizeResponse {
  auth_url: string;
  state: string;
}

export type CalendarEventCategory =
  | 'skonto'
  | 'zahlung_ein'
  | 'zahlung_aus'
  | 'steuer'
  | 'vertrag'
  | 'mahnung';

export type EventUrgency = 'high' | 'medium' | 'low';

export interface CalendarEventPreview {
  uid: string;
  title: string;
  description: string;
  start: string;
  end: string;
  category: CalendarEventCategory;
  urgency: EventUrgency;
}

export interface SyncResult {
  created: number;
  updated: number;
  deleted: number;
  errors: string[];
  synced_at: string;
}

export interface SyncStatus {
  last_sync_at: string | null;
  events_synced: number;
  last_error: string | null;
  is_syncing: boolean;
  provider: CalendarProviderType;
}

export interface CalendarInfo {
  id: string;
  name: string;
  description: string;
  primary: boolean;
  color?: string;
}

export interface CalendarSyncConfig {
  provider: CalendarProviderType;
  enabled: boolean;
  calendar_id: string | null;
  sync_interval_minutes: number;
  categories: string[];
  days_ahead: number;
  caldav_url?: string;
  caldav_username?: string;
}

export interface ConnectionTestRequest {
  provider: string;
  url?: string;
  username?: string;
  password?: string;
}

export interface ConnectionTestResponse {
  success: boolean;
  message: string;
}
