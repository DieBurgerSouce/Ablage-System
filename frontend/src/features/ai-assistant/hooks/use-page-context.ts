/**
 * Page Context Hook
 *
 * Detects the current page context based on the route.
 * Provides context information for the AI assistant.
 */

import { useEffect, useMemo } from 'react';
import { useLocation, useParams, useMatches } from '@tanstack/react-router';
import { useAIAssistantStore, type PageContext, type PageContextType } from '../stores/ai-assistant-store';

interface RouteMatch {
  id: string;
  pathname: string;
  params: Record<string, string>;
}

/**
 * Maps route patterns to page context types.
 */
function getPageContextType(pathname: string): PageContextType {
  // Dashboard
  if (pathname === '/' || pathname === '/dashboard') {
    return 'dashboard';
  }

  // CEO Dashboard
  if (pathname.startsWith('/dashboard/ceo')) {
    return 'ceo-dashboard';
  }

  // Smart Inbox
  if (pathname.startsWith('/inbox')) {
    return 'smart-inbox';
  }

  // Knowledge Graph
  if (pathname.startsWith('/knowledge-graph')) {
    return 'knowledge-graph';
  }

  // Compliance
  if (pathname.startsWith('/compliance')) {
    return 'compliance';
  }

  // OCR Suite
  if (pathname.startsWith('/ocr-suite')) {
    return 'ocr-suite';
  }

  // Documents
  if (pathname.startsWith('/documents')) {
    if (pathname.match(/\/documents\/[a-f0-9-]+$/)) {
      return 'document-detail';
    }
    return 'documents';
  }

  // Ablage (same as documents)
  if (pathname.startsWith('/ablage')) {
    if (pathname.match(/\/ablage\/[a-f0-9-]+$/)) {
      return 'document-detail';
    }
    return 'documents';
  }

  // Entities (Kunden, Lieferanten)
  if (pathname.startsWith('/kunden') || pathname.startsWith('/lieferanten') || pathname.startsWith('/entities')) {
    if (pathname.match(/\/(kunden|lieferanten|entities)\/[a-f0-9-]+$/)) {
      return 'entity-detail';
    }
    return 'entities';
  }

  // Invoices
  if (pathname.startsWith('/invoices') || pathname.startsWith('/rechnungen')) {
    return 'invoices';
  }

  // Banking
  if (pathname.startsWith('/banking') || pathname.startsWith('/konten') || pathname.startsWith('/transaktionen')) {
    return 'banking';
  }

  // Validation
  if (pathname.startsWith('/validation') || pathname.startsWith('/validierung')) {
    return 'validation';
  }

  // Reports
  if (pathname.startsWith('/reports') || pathname.startsWith('/berichte')) {
    return 'reports';
  }

  // Admin
  if (pathname.startsWith('/admin')) {
    return 'admin';
  }

  // Settings
  if (pathname.startsWith('/settings') || pathname.startsWith('/einstellungen')) {
    return 'settings';
  }

  return 'unknown';
}

/**
 * Extracts entity/document IDs from route params.
 */
function extractIds(pathname: string, params: Record<string, string | undefined>): {
  documentId?: string;
  entityId?: string;
} {
  const result: { documentId?: string; entityId?: string } = {};

  // Check params first
  if (params.documentId) {
    result.documentId = params.documentId;
  }
  if (params.entityId) {
    result.entityId = params.entityId;
  }
  if (params.id) {
    // Determine if it's a document or entity based on route
    if (pathname.includes('/documents') || pathname.includes('/ablage')) {
      result.documentId = params.id;
    } else if (pathname.includes('/kunden') || pathname.includes('/lieferanten') || pathname.includes('/entities')) {
      result.entityId = params.id;
    }
  }

  // Extract from pathname if not in params
  if (!result.documentId && !result.entityId) {
    const uuidMatch = pathname.match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/);
    if (uuidMatch) {
      if (pathname.includes('/documents') || pathname.includes('/ablage')) {
        result.documentId = uuidMatch[1];
      } else if (pathname.includes('/kunden') || pathname.includes('/lieferanten') || pathname.includes('/entities')) {
        result.entityId = uuidMatch[1];
      }
    }
  }

  return result;
}

/**
 * Hook to detect and update page context.
 */
export function usePageContext(): PageContext {
  const location = useLocation();
  const params = useParams({ strict: false });
  const setPageContext = useAIAssistantStore((state) => state.setPageContext);
  const currentContext = useAIAssistantStore((state) => state.pageContext);

  const context = useMemo<PageContext>(() => {
    const pathname = location.pathname;
    const type = getPageContextType(pathname);
    const ids = extractIds(pathname, params as Record<string, string | undefined>);

    return {
      type,
      documentId: ids.documentId,
      entityId: ids.entityId,
    };
  }, [location.pathname, params]);

  // Update store when context changes
  useEffect(() => {
    if (
      context.type !== currentContext.type ||
      context.documentId !== currentContext.documentId ||
      context.entityId !== currentContext.entityId
    ) {
      setPageContext(context);
    }
  }, [context, currentContext, setPageContext]);

  return context;
}

/**
 * Get context-aware prompt suggestions based on current page.
 */
export function getContextSuggestions(context: PageContext): string[] {
  switch (context.type) {
    case 'dashboard':
      return [
        'Was sind meine offenen Aufgaben?',
        'Zeige mir die wichtigsten KPIs',
        'Welche Rechnungen sind überfällig?',
        'Analysiere meine Finanzen diesen Monat',
      ];

    case 'ceo-dashboard':
      return [
        'Erkläre den Gesundheitsscore',
        'Welche Anomalien gibt es?',
        'Vergleiche KPIs mit letztem Monat',
        'Was braucht sofortige Aufmerksamkeit?',
      ];

    case 'smart-inbox':
      return [
        'Was hat die höchste Priorität?',
        'Zeige überfällige Rechnungen',
        'Welche Aktionen empfiehlst du?',
        'Fasse die heutigen Eingänge zusammen',
      ];

    case 'knowledge-graph':
      return [
        'Erkläre die Beziehungen dieses Knotens',
        'Finde verbundene Dokumente',
        'Zeige die Dokumenten-Kette',
        'Welche Entitäten sind am stärksten vernetzt?',
      ];

    case 'compliance':
      return [
        'Wie ist der aktuelle Compliance-Status?',
        'Welche Aufbewahrungsfristen laufen ab?',
        'Gibt es DSGVO-Probleme?',
        'Bereite einen Audit-Bericht vor',
      ];

    case 'ocr-suite':
      return [
        'Welche Regionen haben niedrige Konfidenz?',
        'Wie hat sich die OCR-Genauigkeit verbessert?',
        'Vergleiche die beiden Versionen',
        'Zeige häufige OCR-Fehler',
      ];

    case 'documents':
      return [
        'Finde alle Rechnungen von letztem Monat',
        'Zeige mir unbezahlte Rechnungen',
        'Suche nach Verträgen',
        'Welche Dokumente brauchen Aufmerksamkeit?',
      ];

    case 'document-detail':
      return [
        'Fasse dieses Dokument zusammen',
        'Welche Entitäten sind hier erwähnt?',
        'Gibt es ähnliche Dokumente?',
        'Was sind die wichtigsten Informationen?',
      ];

    case 'entities':
      return [
        'Zeige mir High-Risk Kunden',
        'Wer hat offene Rechnungen?',
        'Analysiere Zahlungsverhalten',
        'Finde inaktive Kunden',
      ];

    case 'entity-detail':
      return [
        'Zeige mir alle Dokumente zu diesem Kunden',
        'Wie ist das Zahlungsverhalten?',
        'Gibt es offene Rechnungen?',
        'Erstelle einen Kundenbericht',
      ];

    case 'invoices':
      return [
        'Welche Rechnungen sind überfällig?',
        'Zeige mir Skonto-Möglichkeiten',
        'Analysiere Zahlungseingänge',
        'Welche Rechnungen brauchen Mahnung?',
      ];

    case 'banking':
      return [
        'Zeige offene Transaktionen',
        'Finde nicht zugeordnete Buchungen',
        'Analysiere Kontoumsätze',
        'Welche Zahlungen fehlen noch?',
      ];

    case 'validation':
      return [
        'Zeige mir Items mit niedrigem Confidence',
        'Was muss ich heute validieren?',
        'Batch-genehmige ähnliche Items',
        'Erkläre die OCR-Fehler',
      ];

    case 'reports':
      return [
        'Erstelle einen Monatsbericht',
        'Vergleiche mit Vorjahr',
        'Zeige Umsatzentwicklung',
        'Exportiere für den Steuerberater',
      ];

    case 'admin':
      return [
        'Zeige Systemstatus',
        'Gibt es Performance-Probleme?',
        'Wie viele Dokumente wurden verarbeitet?',
        'Prüfe die Auslastung',
      ];

    case 'settings':
      return [
        'Welche Einstellungen gibt es?',
        'Wie konfiguriere ich OCR?',
        'Erkläre die Optionen',
        'Hilfe zu dieser Seite',
      ];

    default:
      return [
        'Wie kann ich dir helfen?',
        'Suche in meinen Dokumenten',
        'Analysiere meine Daten',
        'Zeige mir offene Aufgaben',
      ];
  }
}

/**
 * Get context-aware placeholder text for input.
 */
export function getContextPlaceholder(context: PageContext): string {
  switch (context.type) {
    case 'dashboard':
      return 'Frage zu deinem Dashboard...';
    case 'ceo-dashboard':
      return 'Frage zum Unternehmens-Dashboard...';
    case 'smart-inbox':
      return 'Frage zu Inbox-Einträgen...';
    case 'knowledge-graph':
      return 'Frage zu Dokumenten-Beziehungen...';
    case 'compliance':
      return 'Frage zu Compliance und Aufbewahrung...';
    case 'ocr-suite':
      return 'Frage zu OCR und Erkennung...';
    case 'documents':
    case 'document-detail':
      return 'Frage zu deinen Dokumenten...';
    case 'entities':
    case 'entity-detail':
      return 'Frage zu Kunden oder Lieferanten...';
    case 'invoices':
      return 'Frage zu Rechnungen...';
    case 'banking':
      return 'Frage zu Transaktionen...';
    case 'validation':
      return 'Frage zur Validierung...';
    case 'reports':
      return 'Frage zu Berichten...';
    case 'admin':
      return 'Frage zur Administration...';
    case 'settings':
      return 'Frage zu Einstellungen...';
    default:
      return 'Wie kann ich dir helfen?';
  }
}
