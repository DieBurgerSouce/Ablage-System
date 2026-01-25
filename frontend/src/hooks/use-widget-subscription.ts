/**
 * Widget Subscription Hooks - Re-export from websocket.ts
 *
 * Phase 4.7: Real-time Widget Updates
 *
 * Diese Datei re-exportiert die Widget-Subscription Hooks aus websocket.ts
 * fuer einfacheren Import in Widget-Komponenten.
 *
 * @example
 * import { useWidgetSubscription, useMultiWidgetSubscription } from '@/hooks/use-widget-subscription';
 *
 * // Einzelnes Widget
 * useWidgetSubscription('cashflow', {
 *   autoInvalidate: true,
 *   queryKeysToInvalidate: [['cashflow'], ['finance']],
 * });
 *
 * // Mehrere Widgets im Dashboard
 * useMultiWidgetSubscription({
 *   cashflow: [['cashflow'], ['finance']],
 *   dunning: [['dunning'], ['invoices']],
 *   recent_documents: [['documents']],
 * });
 */

export {
  useWidgetSubscription,
  useMultiWidgetSubscription,
  useWidgetRefreshTrigger,
  type WidgetType,
  type WidgetUpdatePayload,
} from "@/lib/websocket"

// Widget Query Key Mapping fuer konsistente Verwendung
export const WIDGET_QUERY_KEYS: Record<string, string[][]> = {
  cashflow: [["cashflow"], ["finance"], ["banking"]],
  recent_documents: [["documents"], ["recent-documents"]],
  finance_status: [["finance"], ["finance-status"]],
  dunning: [["dunning"], ["invoices"], ["mahnwesen"]],
  ocr_performance: [["ocr"], ["ocr-performance"], ["metrics"]],
  aging_report: [["aging"], ["aging-report"], ["invoices"]],
  skonto: [["skonto"], ["invoices"]],
  system_status: [["system"], ["health"]],
  today: [["today"], ["tasks"], ["deadlines"]],
  quick_links: [["quick-links"]],
  upload: [["upload"], ["documents"]],
}

/**
 * Hook zum Abonnieren aller Dashboard-Widgets mit Standard-Query-Keys.
 *
 * Vereinfachte Nutzung fuer die Dashboard-Seite.
 *
 * @example
 * function DashboardPage() {
 *   useDashboardWidgetSubscriptions();
 *   return <DashboardWidgets />;
 * }
 */
export function useDashboardWidgetSubscriptions() {
  const { useMultiWidgetSubscription: subscribe } = require("@/lib/websocket")
  subscribe(WIDGET_QUERY_KEYS)
}
