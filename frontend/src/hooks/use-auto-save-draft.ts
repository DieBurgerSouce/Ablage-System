/**
 * useAutoSaveDraft Hook
 *
 * Speichert Formular-Entwuerfe automatisch in localStorage.
 * Stellt Daten nach Navigation oder Fehlern wieder her.
 *
 * Features:
 * - Debounced auto-save (Standard: 2 Sekunden)
 * - Automatische Wiederherstellung beim Mount
 * - Draft-Loeschung nach erfolgreichem Submit
 * - TTL-basierte Ablaufzeit (Standard: 24 Stunden)
 *
 * @example
 * const { draft, updateDraft, clearDraft, hasDraft, lastSavedAt } =
 *   useAutoSaveDraft<InvoiceFormData>('invoice-form-new', {
 *     debounceMs: 1500,
 *     ttlMs: 48 * 60 * 60 * 1000, // 48h
 *   })
 */

import { useCallback, useEffect, useRef, useState } from 'react'

interface DraftEntry<T> {
  data: T
  savedAt: number
  version: number
}

interface UseAutoSaveDraftOptions {
  /** Debounce-Zeit in ms (Standard: 2000) */
  debounceMs?: number
  /** Ablaufzeit in ms (Standard: 24h) */
  ttlMs?: number
  /** Auto-Save aktiviert (Standard: true) */
  enabled?: boolean
}

interface UseAutoSaveDraftResult<T> {
  /** Aktueller Draft oder null */
  draft: T | null
  /** Draft aktualisieren (loest debounced Save aus) */
  updateDraft: (data: T) => void
  /** Draft sofort speichern */
  saveDraft: (data: T) => void
  /** Draft loeschen (nach erfolgreichem Submit) */
  clearDraft: () => void
  /** Ob ein Draft vorhanden ist */
  hasDraft: boolean
  /** Zeitpunkt der letzten Speicherung */
  lastSavedAt: Date | null
}

const DRAFT_PREFIX = 'ablage_draft_'

export function useAutoSaveDraft<T>(
  key: string,
  options: UseAutoSaveDraftOptions = {}
): UseAutoSaveDraftResult<T> {
  const {
    debounceMs = 2000,
    ttlMs = 24 * 60 * 60 * 1000,
    enabled = true,
  } = options

  const storageKey = `${DRAFT_PREFIX}${key}`
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Draft aus localStorage laden
  const [draft, setDraft] = useState<T | null>(() => {
    if (!enabled) return null
    try {
      const raw = window.localStorage.getItem(storageKey)
      if (!raw) return null
      const entry = JSON.parse(raw) as DraftEntry<T>
      // TTL pruefen
      if (Date.now() - entry.savedAt > ttlMs) {
        window.localStorage.removeItem(storageKey)
        return null
      }
      return entry.data
    } catch {
      return null
    }
  })

  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(() => {
    if (!enabled) return null
    try {
      const raw = window.localStorage.getItem(storageKey)
      if (!raw) return null
      const entry = JSON.parse(raw) as DraftEntry<T>
      return new Date(entry.savedAt)
    } catch {
      return null
    }
  })

  const saveDraft = useCallback(
    (data: T) => {
      if (!enabled) return
      try {
        const entry: DraftEntry<T> = {
          data,
          savedAt: Date.now(),
          version: 1,
        }
        window.localStorage.setItem(storageKey, JSON.stringify(entry))
        setDraft(data)
        setLastSavedAt(new Date())
      } catch {
        // localStorage voll oder nicht verfuegbar
      }
    },
    [storageKey, enabled]
  )

  const updateDraft = useCallback(
    (data: T) => {
      if (!enabled) return
      setDraft(data)
      // Debounced save
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      timerRef.current = setTimeout(() => {
        saveDraft(data)
      }, debounceMs)
    },
    [saveDraft, debounceMs, enabled]
  )

  const clearDraft = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
    }
    try {
      window.localStorage.removeItem(storageKey)
    } catch {
      // Ignorieren
    }
    setDraft(null)
    setLastSavedAt(null)
  }, [storageKey])

  // Cleanup bei Unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [])

  return {
    draft,
    updateDraft,
    saveDraft,
    clearDraft,
    hasDraft: draft !== null,
    lastSavedAt,
  }
}

/**
 * Alle abgelaufenen Drafts aufraumen.
 * Kann beim App-Start aufgerufen werden.
 */
export function cleanupExpiredDrafts(ttlMs: number = 24 * 60 * 60 * 1000): number {
  let cleaned = 0
  try {
    const keys = Object.keys(window.localStorage)
    const now = Date.now()
    for (const key of keys) {
      if (!key.startsWith(DRAFT_PREFIX)) continue
      try {
        const raw = window.localStorage.getItem(key)
        if (!raw) continue
        const entry = JSON.parse(raw) as DraftEntry<unknown>
        if (now - entry.savedAt > ttlMs) {
          window.localStorage.removeItem(key)
          cleaned++
        }
      } catch {
        // Korrupte Eintraege loeschen
        window.localStorage.removeItem(key)
        cleaned++
      }
    }
  } catch {
    // localStorage nicht verfuegbar
  }
  return cleaned
}
