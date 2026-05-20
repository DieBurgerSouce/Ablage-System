/**
 * Default Layout Templates
 *
 * Vorkonfigurierte Dashboard-Layouts für verschiedene Benutzerrollen.
 * Diese Templates werden beim Erstellen neuer Dashboards oder bei
 * der Zurücksetzung auf Werkseinstellungen verwendet.
 *
 * Phase 4.1 der Feature-Roadmap (Januar 2026)
 */

import type { WidgetItem, UserRole, DashboardPreset } from '../stores/useDashboardStore';

// ==================== Types ====================

export interface LayoutTemplate extends DashboardPreset {
  /** Ob dieses Template das Standard-Layout für die Rolle ist */
  isDefault?: boolean;
  /** Tags für Kategorisierung (z.B. "minimal", "vollständig", "finanzen") */
  tags?: string[];
  /** Vorschaubild-URL (optional) */
  previewImageUrl?: string;
  /** Minimale Benutzerrolle für Zugriff */
  minRole?: UserRole;
}

// ==================== Role Hierarchy ====================

/**
 * Rollen-Hierarchie für Berechtigungsprüfung.
 * Höherer Wert = mehr Berechtigungen.
 */
export const ROLE_HIERARCHY: Record<UserRole, number> = {
  user: 1,
  accountant: 2,
  manager: 3,
  admin: 4,
};

/**
 * Prüft ob eine Rolle mindestens so hoch ist wie eine andere.
 */
export function hasMinRole(userRole: UserRole, minRole: UserRole): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[minRole];
}

// ==================== Default Widgets ====================

/**
 * Standard-Widget-Konfigurationen für schnelles Hinzufügen.
 */
export const DEFAULT_WIDGET_CONFIGS: Record<string, Partial<WidgetItem>> = {
  'today': { w: 4, h: 3 },
  'system-status': { w: 4, h: 3 },
  'finance-status': { w: 4, h: 3 },
  'quick-links': { w: 4, h: 2 },
  'upload': { w: 6, h: 4 },
  'recent-documents': { w: 6, h: 4 },
  'open-invoices': { w: 6, h: 3 },
  'skonto': { w: 6, h: 3 },
  'cashflow': { w: 6, h: 4 },
  'aging-report': { w: 6, h: 4 },
  'documents-today': { w: 6, h: 4 },
  'portfolio-summary': { w: 6, h: 4 },
  'property-kpis': { w: 6, h: 3 },
  'insurance-coverage': { w: 4, h: 3 },
  'approvals-pending': { w: 4, h: 3 },
  'activity-feed': { w: 4, h: 5 },
};

// ==================== Layout Templates ====================

/**
 * Standard-Layout für normale Benutzer.
 * Ausgewogene Mischung aus Information, Aktionen und Daten.
 */
export const USER_DEFAULT_LAYOUT: LayoutTemplate = {
  id: 'default',
  name: 'Standard',
  description: 'Ausgewogene Ansicht für alle Benutzer mit den wichtigsten Funktionen',
  role: 'user',
  isDefault: true,
  tags: ['standard', 'ausgewogen'],
  widgets: [
    { id: 'today-1', type: 'today', x: 0, y: 0, w: 4, h: 3 },
    { id: 'system-1', type: 'system-status', x: 4, y: 0, w: 4, h: 3 },
    { id: 'finance-1', type: 'finance-status', x: 8, y: 0, w: 4, h: 3 },
    { id: 'quick-1', type: 'quick-links', x: 0, y: 3, w: 4, h: 2 },
    { id: 'upload-1', type: 'upload', x: 4, y: 3, w: 4, h: 3 },
    { id: 'recent-1', type: 'recent-documents', x: 8, y: 3, w: 4, h: 3 },
  ],
};

/**
 * Finanz-fokussiertes Layout für Buchhalter.
 * Schwerpunkt auf Cashflow, Mahnungen und Fälligkeiten.
 */
export const ACCOUNTANT_DEFAULT_LAYOUT: LayoutTemplate = {
  id: 'finance-focus',
  name: 'Finanzen',
  description: 'Fokus auf Finanzkennzahlen, Cashflow und Mahnwesen',
  role: 'accountant',
  isDefault: true,
  tags: ['finanzen', 'buchhalter', 'cashflow'],
  widgets: [
    { id: 'finance-1', type: 'finance-status', x: 0, y: 0, w: 6, h: 3 },
    { id: 'cashflow-1', type: 'cashflow', x: 6, y: 0, w: 6, h: 4 },
    { id: 'aging-1', type: 'aging-report', x: 0, y: 3, w: 6, h: 4 },
    { id: 'dunning-1', type: 'open-invoices', x: 6, y: 4, w: 6, h: 3 },
    { id: 'skonto-1', type: 'skonto', x: 0, y: 7, w: 6, h: 3 },
    { id: 'recent-1', type: 'recent-documents', x: 6, y: 7, w: 6, h: 3 },
  ],
};

/**
 * Management-Übersicht für Führungskräfte.
 * KPIs, Aktivitäten und Genehmigungen auf einen Blick.
 */
export const MANAGER_DEFAULT_LAYOUT: LayoutTemplate = {
  id: 'manager-overview',
  name: 'Management',
  description: 'KPIs und Überblick für Führungskräfte mit Genehmigungsworkflow',
  role: 'manager',
  isDefault: true,
  tags: ['management', 'kpi', 'übersicht'],
  minRole: 'manager',
  widgets: [
    { id: 'today-1', type: 'today', x: 0, y: 0, w: 4, h: 4 },
    { id: 'finance-1', type: 'finance-status', x: 4, y: 0, w: 4, h: 3 },
    { id: 'system-1', type: 'system-status', x: 8, y: 0, w: 4, h: 3 },
    { id: 'activity-1', type: 'activity-feed', x: 8, y: 3, w: 4, h: 5 },
    { id: 'cashflow-1', type: 'cashflow', x: 0, y: 4, w: 8, h: 4 },
    { id: 'approvals-1', type: 'approvals-pending', x: 4, y: 3, w: 4, h: 1 },
  ],
};

/**
 * Vollständige Admin-Übersicht.
 * System-Status, OCR-Performance und Live-Aktivitäten.
 */
export const ADMIN_DEFAULT_LAYOUT: LayoutTemplate = {
  id: 'admin-full',
  name: 'Administration',
  description: 'Vollständige Systemübersicht für Administratoren',
  role: 'admin',
  isDefault: true,
  tags: ['admin', 'system', 'vollständig'],
  minRole: 'admin',
  widgets: [
    { id: 'system-1', type: 'system-status', x: 0, y: 0, w: 4, h: 3 },
    { id: 'ocr-1', type: 'documents-today', x: 4, y: 0, w: 4, h: 4 },
    { id: 'activity-1', type: 'activity-feed', x: 8, y: 0, w: 4, h: 5 },
    { id: 'today-1', type: 'today', x: 0, y: 3, w: 4, h: 3 },
    { id: 'upload-1', type: 'upload', x: 4, y: 4, w: 4, h: 3 },
    { id: 'recent-1', type: 'recent-documents', x: 0, y: 6, w: 8, h: 3 },
  ],
};

/**
 * Minimales Layout für schnellen Zugriff.
 * Nur die wichtigsten Widgets für schnelle Bedienung.
 */
export const MINIMAL_LAYOUT: LayoutTemplate = {
  id: 'minimal',
  name: 'Minimal',
  description: 'Kompakte Ansicht mit nur wesentlichen Widgets',
  role: 'user',
  tags: ['minimal', 'kompakt', 'schnell'],
  widgets: [
    { id: 'today-1', type: 'today', x: 0, y: 0, w: 6, h: 3 },
    { id: 'quick-1', type: 'quick-links', x: 6, y: 0, w: 6, h: 2 },
    { id: 'upload-1', type: 'upload', x: 0, y: 3, w: 6, h: 3 },
    { id: 'recent-1', type: 'recent-documents', x: 6, y: 2, w: 6, h: 4 },
  ],
};

/**
 * Portfolio-fokussiertes Layout für Vermögensverwaltung.
 */
export const PORTFOLIO_LAYOUT: LayoutTemplate = {
  id: 'portfolio',
  name: 'Portfolio',
  description: 'Vermögensübersicht mit Immobilien, Versicherungen und Anlagen',
  role: 'user',
  tags: ['portfolio', 'vermögen', 'privat'],
  widgets: [
    { id: 'portfolio-1', type: 'portfolio-summary', x: 0, y: 0, w: 6, h: 4 },
    { id: 'property-1', type: 'property-kpis', x: 6, y: 0, w: 6, h: 3 },
    { id: 'insurance-1', type: 'insurance-coverage', x: 6, y: 3, w: 6, h: 3 },
    { id: 'cashflow-1', type: 'cashflow', x: 0, y: 4, w: 6, h: 4 },
    { id: 'today-1', type: 'today', x: 0, y: 8, w: 4, h: 3 },
    { id: 'recent-1', type: 'recent-documents', x: 4, y: 8, w: 8, h: 3 },
  ],
};

// ==================== Exported Collections ====================

/**
 * Alle verfügbaren Layout-Templates.
 */
export const ALL_LAYOUT_TEMPLATES: LayoutTemplate[] = [
  USER_DEFAULT_LAYOUT,
  ACCOUNTANT_DEFAULT_LAYOUT,
  MANAGER_DEFAULT_LAYOUT,
  ADMIN_DEFAULT_LAYOUT,
  MINIMAL_LAYOUT,
  PORTFOLIO_LAYOUT,
];

/**
 * Standard-Templates pro Rolle.
 */
export const DEFAULT_LAYOUTS_BY_ROLE: Record<UserRole, LayoutTemplate> = {
  user: USER_DEFAULT_LAYOUT,
  accountant: ACCOUNTANT_DEFAULT_LAYOUT,
  manager: MANAGER_DEFAULT_LAYOUT,
  admin: ADMIN_DEFAULT_LAYOUT,
};

/**
 * Gibt das Standard-Layout für eine Benutzerrolle zurück.
 */
export function getDefaultLayoutForRole(role: UserRole): LayoutTemplate {
  return DEFAULT_LAYOUTS_BY_ROLE[role] || USER_DEFAULT_LAYOUT;
}

/**
 * Gibt alle verfügbaren Templates für eine Benutzerrolle zurück.
 * Filtert Templates basierend auf minRole.
 */
export function getAvailableTemplatesForRole(role: UserRole): LayoutTemplate[] {
  return ALL_LAYOUT_TEMPLATES.filter((template) => {
    if (!template.minRole) return true;
    return hasMinRole(role, template.minRole);
  });
}

/**
 * Findet ein Template anhand seiner ID.
 */
export function getTemplateById(id: string): LayoutTemplate | undefined {
  return ALL_LAYOUT_TEMPLATES.find((t) => t.id === id);
}

/**
 * Filtert Templates nach Tags.
 */
export function getTemplatesByTag(tag: string): LayoutTemplate[] {
  return ALL_LAYOUT_TEMPLATES.filter((t) => t.tags?.includes(tag));
}
