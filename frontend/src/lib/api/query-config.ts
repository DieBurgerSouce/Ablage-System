/**
 * Standardisierte Query-Cache-Konfiguration.
 *
 * Kategorien nach Daten-Volatilitaet.
 * Alle TanStack Query Hooks sollen diese Konstanten verwenden,
 * um konsistente Cache-Zeiten im gesamten Frontend sicherzustellen.
 */

/** Echtzeit-Daten (WebSocket-basiert, Live-Status) */
export const QUERY_REALTIME = {
  staleTime: 5 * 1000,
  gcTime: 30 * 1000,
} as const;

/** Volatile Listen (Dokumente, Jobs, Queues, Transaktionen) */
export const QUERY_VOLATILE = {
  staleTime: 30 * 1000,
  gcTime: 5 * 60 * 1000,
} as const;

/** Standard-Detail-Ansichten (Einzel-Dokument, Regel-Detail) */
export const QUERY_STANDARD = {
  staleTime: 60 * 1000,
  gcTime: 10 * 60 * 1000,
} as const;

/** Semi-statische Daten (User-Profile, Firmen-Info, Team-Listen) */
export const QUERY_SEMI_STATIC = {
  staleTime: 5 * 60 * 1000,
  gcTime: 30 * 60 * 1000,
} as const;

/** Statische Konfiguration (Enums, Formate, Feature Flags) */
export const QUERY_STATIC = {
  staleTime: 60 * 60 * 1000,
  gcTime: 2 * 60 * 60 * 1000,
} as const;

/** KPIs und Statistiken */
export const QUERY_KPIS = {
  staleTime: 60 * 1000,
  gcTime: 10 * 60 * 1000,
} as const;
