/**
 * useFormDefaults - Merkt sich zuletzt verwendete Formularwerte
 *
 * Speichert die letzten Eingaben pro Formular in localStorage,
 * damit Felder beim nächsten Öffnen vorausgefüllt werden können.
 * Werte verfallen automatisch nach 30 Tagen.
 *
 * @example
 * ```tsx
 * const { getDefault, recordValues, clearDefaults } = useFormDefaults('invoice-form');
 * const defaultCurrency = getDefault('currency', 'EUR');
 * ```
 */

import { useCallback, useMemo } from 'react';
import { useLocalStorage } from './use-local-storage';

// ==================== Types ====================

type PrimitiveValue = string | number | boolean;

interface FormDefaultsEntry {
  values: Record<string, PrimitiveValue>;
  timestamp: number;
}

interface UseFormDefaultsReturn {
  /** Standardwert für ein Feld abrufen, mit Fallback */
  getDefault: <V extends PrimitiveValue>(fieldName: string, fallback: V) => V;
  /** Aktuelle Formularwerte für zukünftige Nutzung speichern */
  recordValues: (values: Record<string, PrimitiveValue>) => void;
  /** Alle gespeicherten Standardwerte für dieses Formular löschen */
  clearDefaults: () => void;
  /** Ob gespeicherte Standardwerte vorhanden sind */
  hasDefaults: boolean;
}

// ==================== Constants ====================

/** 30 Tage in Millisekunden */
const EXPIRY_MS = 30 * 24 * 60 * 60 * 1000;

// ==================== Hook ====================

export function useFormDefaults(formId: string): UseFormDefaultsReturn {
  const storageKey = `ablage-form-defaults-${formId}`;
  const [entry, setEntry] = useLocalStorage<FormDefaultsEntry | null>(storageKey, null);

  const isExpired = useMemo(() => {
    if (!entry) return true;
    return Date.now() - entry.timestamp > EXPIRY_MS;
  }, [entry]);

  const getDefault = useCallback(
    <V extends PrimitiveValue>(fieldName: string, fallback: V): V => {
      if (!entry || isExpired) return fallback;
      const stored = entry.values[fieldName];
      if (stored === undefined) return fallback;
      return stored as V;
    },
    [entry, isExpired]
  );

  const recordValues = useCallback(
    (values: Record<string, PrimitiveValue>) => {
      setEntry({
        values,
        timestamp: Date.now(),
      });
    },
    [setEntry]
  );

  const clearDefaults = useCallback(() => {
    setEntry(null);
  }, [setEntry]);

  const hasDefaults = entry !== null && !isExpired;

  return {
    getDefault,
    recordValues,
    clearDefaults,
    hasDefaults,
  };
}
