/**
 * Settings Model Types
 *
 * Typen für Benutzer-Praeferenzen und Firmeneinstellungen.
 */

// ==================== User Preferences ====================

/**
 * Theme-Einstellung
 */
export type ThemeMode = 'light' | 'dark' | 'system';

/**
 * Display-Modus für Dokument-Viewer
 */
export type DisplayMode = 'light' | 'dark' | 'whitescreen' | 'blackscreen';

/**
 * Sprache
 */
export type Language = 'de' | 'en';

/**
 * Datumsformat
 */
export type DateFormat = 'DD.MM.YYYY' | 'YYYY-MM-DD' | 'MM/DD/YYYY';

/**
 * Zeitformat
 */
export type TimeFormat = '24h' | '12h';

/**
 * Benachrichtigungs-Praeferenzen
 */
export interface NotificationPreferences {
  /** Email-Benachrichtigungen aktiviert */
  email_enabled: boolean;
  /** Push-Benachrichtigungen aktiviert */
  push_enabled: boolean;
  /** Benachrichtigung bei neuen Dokumenten */
  on_document_processed: boolean;
  /** Benachrichtigung bei Fehlern */
  on_processing_error: boolean;
  /** Benachrichtigung bei Genehmigungsanfragen */
  on_approval_request: boolean;
  /** Benachrichtigung bei Fristen */
  on_deadline_approaching: boolean;
  /** Benachrichtigung bei Systemwarnungen */
  on_system_alert: boolean;
  /** Tägliche Zusammenfassung */
  daily_digest: boolean;
  /** Wöchentliche Zusammenfassung */
  weekly_digest: boolean;
  /** Digest-Uhrzeit (HH:MM) */
  digest_time: string;
}

/**
 * Dashboard-Praeferenzen
 */
export interface DashboardPreferences {
  /** Standard-Zeitraum für Metriken */
  default_period: '7d' | '30d' | '90d' | '1y';
  /** Sichtbare Widgets */
  visible_widgets: string[];
  /** Widget-Layout */
  widget_layout: Record<string, { x: number; y: number; w: number; h: number }>;
  /** Kompakte Ansicht */
  compact_view: boolean;
  /** Auto-Refresh Intervall (Sekunden, 0 = deaktiviert) */
  auto_refresh_seconds: number;
}

/**
 * Tabellen-Praeferenzen
 */
export interface TablePreferences {
  /** Standard-Seitengröße */
  default_page_size: 10 | 25 | 50 | 100;
  /** Sichtbare Spalten pro Tabelle */
  visible_columns: Record<string, string[]>;
  /** Standard-Sortierung pro Tabelle */
  default_sort: Record<string, { column: string; direction: 'asc' | 'desc' }>;
  /** Kompakte Zeilen */
  dense_rows: boolean;
}

/**
 * Onboarding-Status
 */
export interface OnboardingStatus {
  /** Onboarding abgeschlossen */
  completed: boolean;
  /** Onboarding übersprungen */
  skipped: boolean;
  /** Abgeschlossene Schritte */
  completed_steps: string[];
  /** Letzter Schritt */
  last_step: string | null;
  /** Begonnen am */
  started_at: string | null;
  /** Abgeschlossen am */
  completed_at: string | null;
}

/**
 * Tooltip-Praeferenzen
 */
export interface TooltipPreferences {
  /** Tooltips aktiviert */
  enabled: boolean;
  /** Versteckte Tooltips (Feature-IDs) */
  dismissed_tooltips: string[];
}

/**
 * Vollständige Benutzer-Praeferenzen
 */
export interface UserPreferences {
  /** Theme */
  theme: ThemeMode;
  /** Display-Modus für Viewer */
  display_mode: DisplayMode;
  /** Sprache */
  language: Language;
  /** Datumsformat */
  date_format: DateFormat;
  /** Zeitformat */
  time_format: TimeFormat;
  /** Benachrichtigungen */
  notifications: NotificationPreferences;
  /** Dashboard */
  dashboard: DashboardPreferences;
  /** Tabellen */
  tables: TablePreferences;
  /** Onboarding */
  onboarding: OnboardingStatus;
  /** Tooltips */
  tooltips: TooltipPreferences;
  /** Sidebar minimiert */
  sidebar_collapsed: boolean;
  /** Tastenkürzel aktiviert */
  keyboard_shortcuts_enabled: boolean;
  /** Animationen reduziert (a11y) */
  reduced_motion: boolean;
  /** Hoher Kontrast (a11y) */
  high_contrast: boolean;
  /** Schriftgröße-Multiplikator */
  font_size_multiplier: number;
}

/**
 * Benutzer-Praeferenzen aktualisieren
 */
export interface UserPreferencesUpdate extends Partial<UserPreferences> {}

// ==================== Company Settings ====================

/**
 * OCR-Einstellungen
 */
export interface OCRSettings {
  /** Standard-Backend */
  default_backend: 'auto' | 'deepseek' | 'got_ocr' | 'surya' | 'surya_gpu';
  /** Auto-Verarbeitung aktiviert */
  auto_process_enabled: boolean;
  /** Minimale Confidence für Auto-Accept */
  auto_accept_confidence: number;
  /** Unterstützte Sprachen */
  supported_languages: string[];
  /** Tabellenerkennung aktiviert */
  table_detection_enabled: boolean;
  /** Formelerkennung aktiviert */
  formula_detection_enabled: boolean;
}

/**
 * Rechnungs-Einstellungen
 */
export interface InvoiceSettings {
  /** Standard-Zahlungsziel (Tage) */
  default_payment_terms_days: number;
  /** Skonto-Standard (Prozent) */
  default_skonto_percent: number;
  /** Skonto-Frist (Tage) */
  default_skonto_days: number;
  /** Automatische Mahnstufen-Erhöhung */
  auto_dunning_enabled: boolean;
  /** Mahnstufen-Konfiguration */
  dunning_levels: DunningLevelConfig[];
}

/**
 * Mahnstufen-Konfiguration
 */
export interface DunningLevelConfig {
  level: number;
  days_overdue: number;
  fee_amount: number;
  email_template_id: string | null;
  auto_send_email: boolean;
}

/**
 * Approval-Einstellungen
 */
export interface ApprovalSettings {
  /** Genehmigung erforderlich ab Betrag */
  approval_threshold_amount: number;
  /** Eskalation nach Stunden */
  escalation_after_hours: number;
  /** Standard-Genehmiger (User-IDs) */
  default_approvers: string[];
  /** Mehrstufige Genehmigung aktiviert */
  multi_level_approval_enabled: boolean;
}

/**
 * Sicherheits-Einstellungen
 */
export interface SecuritySettings {
  /** MFA erzwingen */
  mfa_required: boolean;
  /** Session-Timeout (Minuten) */
  session_timeout_minutes: number;
  /** Passwort-Ablauf (Tage, 0 = nie) */
  password_expiry_days: number;
  /** Minimale Passwort-Länge */
  min_password_length: number;
  /** Passwort-Komplexitaet erzwingen */
  require_complex_password: boolean;
  /** IP-Whitelist aktiviert */
  ip_whitelist_enabled: boolean;
  /** Erlaubte IPs */
  allowed_ips: string[];
}

/**
 * DLP-Einstellungen (Data Loss Prevention)
 */
export interface DLPSettings {
  /** DLP aktiviert */
  enabled: boolean;
  /** Download-Wasserzeichen aktiviert */
  watermark_enabled: boolean;
  /** Wasserzeichen-Text */
  watermark_text: string;
  /** Download-Beschränkungen aktiv */
  download_restrictions_enabled: boolean;
  /** Sensible Daten maskieren */
  mask_sensitive_data: boolean;
}

/**
 * Integration-Einstellungen
 */
export interface IntegrationSettings {
  /** DATEV aktiviert */
  datev_enabled: boolean;
  /** DATEV-Berater-Nummer */
  datev_consultant_number: string | null;
  /** DATEV-Mandanten-Nummer */
  datev_client_number: string | null;
  /** Lexware aktiviert */
  lexware_enabled: boolean;
  /** Slack aktiviert */
  slack_enabled: boolean;
  /** Slack Webhook URL */
  slack_webhook_url: string | null;
  /** Slack Default Channel */
  slack_default_channel: string | null;
}

/**
 * Vollständige Firmeneinstellungen
 */
export interface CompanySettings {
  company_id: string;
  ocr: OCRSettings;
  invoices: InvoiceSettings;
  approvals: ApprovalSettings;
  security: SecuritySettings;
  dlp: DLPSettings;
  integrations: IntegrationSettings;
  /** Letzte Aktualisierung */
  updated_at: string;
  /** Aktualisiert von */
  updated_by_id: string | null;
}

/**
 * Firmeneinstellungen aktualisieren
 */
export interface CompanySettingsUpdate {
  ocr?: Partial<OCRSettings>;
  invoices?: Partial<InvoiceSettings>;
  approvals?: Partial<ApprovalSettings>;
  security?: Partial<SecuritySettings>;
  dlp?: Partial<DLPSettings>;
  integrations?: Partial<IntegrationSettings>;
}

// ==================== Feature Flags ====================

/**
 * Feature Flags
 */
export interface FeatureFlags {
  /** Holding-Dashboard aktiviert */
  holding_dashboard: boolean;
  /** Fraud Detection aktiviert */
  fraud_detection: boolean;
  /** Predictive Cash Flow aktiviert */
  predictive_cashflow: boolean;
  /** Risk Intelligence aktiviert */
  risk_intelligence: boolean;
  /** AI Chat aktiviert */
  ai_chat: boolean;
  /** Beta-Features anzeigen */
  show_beta_features: boolean;
}

// ==================== Subscription ====================

/**
 * Subscription-Tier
 */
export type SubscriptionTier = 'free' | 'basic' | 'professional' | 'enterprise';

/**
 * Subscription-Status
 */
export type SubscriptionStatus = 'active' | 'trialing' | 'past_due' | 'cancelled' | 'paused';

/**
 * Subscription
 */
export interface Subscription {
  id: string;
  company_id: string;
  tier: SubscriptionTier;
  status: SubscriptionStatus;
  /** Maximale Benutzer */
  max_users: number;
  /** Maximaler Speicher (Bytes) */
  max_storage_bytes: number;
  /** Maximale Dokumente pro Monat */
  max_documents_per_month: number;
  /** Features */
  features: FeatureFlags;
  /** Startdatum */
  started_at: string;
  /** Enddatum (bei Kündigung) */
  ends_at: string | null;
  /** Nächste Abrechnung */
  next_billing_at: string | null;
}
