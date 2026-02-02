/**
 * Notification Preferences Types
 *
 * Type-Definitionen fuer das erweiterte Benachrichtigungssystem.
 * Basiert auf UnifiedNotificationHub Backend-Modellen.
 */

/**
 * Verfuegbare Benachrichtigungskanaele.
 */
export type NotificationChannel =
  | 'email'
  | 'slack'
  | 'teams'
  | 'push'
  | 'sms'
  | 'whatsapp'
  | 'in_app'
  | 'websocket';

/**
 * Schweregrad einer Benachrichtigung.
 */
export type NotificationSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

/**
 * Kategorien von Benachrichtigungen.
 */
export type NotificationCategory =
  | 'document'
  | 'alert'
  | 'workflow'
  | 'system'
  | 'security'
  | 'finance'
  | 'compliance'
  | 'reminder';

/**
 * Eskalationsstufen.
 */
export type EscalationLevel = 0 | 1 | 2 | 3 | 4 | 5;

/**
 * Wochentag fuer Ruhezeiten.
 */
export type Weekday = 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday';

/**
 * Kanal-Konfiguration.
 */
export interface ChannelConfig {
  channel: NotificationChannel;
  enabled: boolean;
  configured: boolean;
  description: string;
  gdprRequired?: boolean;
  requiresPhone?: boolean;
}

/**
 * Schweregrad-Matrix-Eintrag.
 * Definiert welche Kanaele bei welchem Schweregrad aktiviert sind.
 */
export interface SeverityChannelMapping {
  severity: NotificationSeverity;
  channels: NotificationChannel[];
}

/**
 * Ruhezeiten-Konfiguration.
 */
export interface QuietHoursConfig {
  enabled: boolean;
  startHour: number; // 0-23
  endHour: number; // 0-23
  timezone: string;
  weekdays: Weekday[];
  skipCritical: boolean; // Kritische Alerts trotzdem senden
}

/**
 * Eskalationsketten-Stufe.
 */
export interface EscalationStep {
  level: EscalationLevel;
  delayMinutes: number;
  channels: NotificationChannel[];
  description: string;
}

/**
 * Vollstaendige Benachrichtigungs-Praeferenzen.
 */
export interface NotificationPreferences {
  // Globale Einstellungen
  enabled: boolean;

  // Kanal-Praeferenzen
  emailEnabled: boolean;
  slackEnabled: boolean;
  teamsEnabled: boolean;
  pushEnabled: boolean;
  smsEnabled: boolean;
  whatsappEnabled: boolean;
  inAppEnabled: boolean;

  // Kategorie-Praeferenzen pro Kanal
  emailCategories: NotificationCategory[];
  pushCategories: NotificationCategory[];
  smsCategories: NotificationCategory[];

  // Minimum-Schweregrad pro Kanal
  emailMinSeverity: NotificationSeverity;
  pushMinSeverity: NotificationSeverity;
  smsMinSeverity: NotificationSeverity;

  // Ruhezeiten
  quietHours: QuietHoursConfig;

  // Eskalations-Praeferenzen
  escalationEnabled: boolean;
  escalationPhone: string | null;

  // Metadaten
  lastUpdated: string;
}

/**
 * API Response fuer Praeferenzen.
 */
export interface NotificationPreferencesResponse {
  preferences: NotificationPreferences;
  channelStatus: ChannelConfig[];
  escalationChain: EscalationStep[];
}

/**
 * Update Request fuer Praeferenzen.
 */
export interface UpdateNotificationPreferencesRequest {
  enabled?: boolean;
  emailEnabled?: boolean;
  slackEnabled?: boolean;
  teamsEnabled?: boolean;
  pushEnabled?: boolean;
  smsEnabled?: boolean;
  whatsappEnabled?: boolean;
  inAppEnabled?: boolean;
  emailCategories?: NotificationCategory[];
  pushCategories?: NotificationCategory[];
  smsCategories?: NotificationCategory[];
  emailMinSeverity?: NotificationSeverity;
  pushMinSeverity?: NotificationSeverity;
  smsMinSeverity?: NotificationSeverity;
  quietHours?: Partial<QuietHoursConfig>;
  escalationEnabled?: boolean;
  escalationPhone?: string | null;
}

/**
 * Test-Notification Request.
 */
export interface TestNotificationRequest {
  channel: NotificationChannel;
  message?: string;
}

/**
 * Test-Notification Response.
 */
export interface TestNotificationResponse {
  success: boolean;
  channel: NotificationChannel;
  message: string;
  deliveredAt?: string;
  errorMessage?: string;
}

/**
 * Severity-Matrix Update Request.
 */
export interface UpdateSeverityMatrixRequest {
  severity: NotificationSeverity;
  channels: NotificationChannel[];
}

/**
 * Hilfs-Konstanten fuer UI.
 */
export const CHANNEL_LABELS: Record<NotificationChannel, string> = {
  email: 'E-Mail',
  slack: 'Slack',
  teams: 'Microsoft Teams',
  push: 'Push-Benachrichtigung',
  sms: 'SMS',
  whatsapp: 'WhatsApp',
  in_app: 'In-App',
  websocket: 'Echtzeit (WebSocket)',
};

export const CHANNEL_ICONS: Record<NotificationChannel, string> = {
  email: 'Mail',
  slack: 'Hash',
  teams: 'Users',
  push: 'Bell',
  sms: 'Smartphone',
  whatsapp: 'MessageCircle',
  in_app: 'Inbox',
  websocket: 'Zap',
};

export const SEVERITY_LABELS: Record<NotificationSeverity, string> = {
  info: 'Information',
  low: 'Niedrig',
  medium: 'Mittel',
  high: 'Hoch',
  critical: 'Kritisch',
};

export const SEVERITY_COLORS: Record<NotificationSeverity, string> = {
  info: 'bg-blue-100 text-blue-800',
  low: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  high: 'bg-orange-100 text-orange-800',
  critical: 'bg-red-100 text-red-800',
};

export const CATEGORY_LABELS: Record<NotificationCategory, string> = {
  document: 'Dokumente',
  alert: 'Warnungen',
  workflow: 'Workflows',
  system: 'System',
  security: 'Sicherheit',
  finance: 'Finanzen',
  compliance: 'Compliance',
  reminder: 'Erinnerungen',
};

export const WEEKDAY_LABELS: Record<Weekday, string> = {
  monday: 'Mo',
  tuesday: 'Di',
  wednesday: 'Mi',
  thursday: 'Do',
  friday: 'Fr',
  saturday: 'Sa',
  sunday: 'So',
};

export const ALL_WEEKDAYS: Weekday[] = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
];

export const DEFAULT_QUIET_HOURS: QuietHoursConfig = {
  enabled: false,
  startHour: 22,
  endHour: 7,
  timezone: 'Europe/Berlin',
  weekdays: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
  skipCritical: true,
};

export const DEFAULT_ESCALATION_CHAIN: EscalationStep[] = [
  { level: 1, delayMinutes: 0, channels: ['email', 'slack'], description: 'E-Mail + Slack' },
  { level: 2, delayMinutes: 15, channels: ['email', 'slack', 'teams'], description: '+ Teams' },
  { level: 3, delayMinutes: 30, channels: ['email', 'slack', 'teams', 'push'], description: '+ Push' },
  { level: 4, delayMinutes: 60, channels: ['email', 'slack', 'teams', 'push', 'sms'], description: '+ SMS' },
  { level: 5, delayMinutes: 120, channels: ['email', 'slack', 'teams', 'push', 'sms', 'whatsapp'], description: '+ WhatsApp' },
];
