/**
 * Offline Queue Store
 *
 * Zustand-Store zum Verfolgen von ausstehenden Änderungen
 * die synchronisiert werden müssen, wenn wieder online.
 *
 * Features:
 * - Persistenz in IndexedDB
 * - Zählt ausstehende Mutationen
 * - Verfolgt Sync-Status
 * - Automatische Synchronisation bei Online-Status
 * - Integration mit TanStack Query Mutations
 */

import { create } from 'zustand'
import {
  addMutation,
  getPendingMutations,
  removeMutation,
  updateMutationStatus,
  getPendingMutationCount,
  type OfflineMutation,
} from '@/lib/storage/indexed-db'
import { logger } from '@/lib/logger'

// ==================== Types ====================

export interface PendingMutation {
  id: string
  type: string
  description: string
  endpoint: string
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  payload: unknown
  timestamp: number
  retryCount: number
  status: 'pending' | 'processing' | 'failed'
  errorMessage?: string
}

interface OfflineQueueState {
  /** Ausstehende Änderungen (in-memory cache) */
  pendingMutations: PendingMutation[]

  /** Store initialized from IndexedDB */
  isInitialized: boolean

  /** Sync in progress */
  isSyncing: boolean

  /** Letzter erfolgreicher Sync-Zeitpunkt */
  lastSyncedAt: number | null

  /** Anzahl der ausstehenden Änderungen */
  pendingCount: number
}

interface OfflineQueueActions {
  /** Initialisiert den Store aus IndexedDB */
  initialize: () => Promise<void>

  /** Fuegt eine ausstehende Mutation hinzu */
  addPendingMutation: (mutation: {
    type: string
    description: string
    endpoint: string
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
    payload: unknown
    maxRetries?: number
  }) => Promise<string>

  /** Entfernt eine Mutation nach erfolgreichem Sync */
  removePendingMutation: (id: string) => Promise<void>

  /** Aktualisiert den Status einer Mutation */
  updateMutationStatus: (
    id: string,
    status: PendingMutation['status'],
    errorMessage?: string
  ) => Promise<void>

  /** Markiert Sync als gestartet */
  startSync: () => void

  /** Markiert Sync als beendet */
  finishSync: (success: boolean) => void

  /** Verarbeitet alle ausstehenden Mutationen */
  processQueue: (
    processor: (mutation: PendingMutation) => Promise<boolean>
  ) => Promise<{ success: number; failed: number }>

  /** Laedt die Mutationen aus IndexedDB neu */
  refresh: () => Promise<void>

  /** Löscht alle ausstehenden Mutationen */
  clearPendingMutations: () => Promise<void>

  /** Setzt den Store zurück */
  reset: () => void
}

type OfflineQueueStore = OfflineQueueState & OfflineQueueActions

// ==================== Initial State ====================

const initialState: OfflineQueueState = {
  pendingMutations: [],
  isInitialized: false,
  isSyncing: false,
  lastSyncedAt: null,
  pendingCount: 0,
}

// ==================== Store ====================

export const useOfflineQueueStore = create<OfflineQueueStore>((set, get) => ({
  ...initialState,

  initialize: async () => {
    if (get().isInitialized) return

    try {
      const mutations = await getPendingMutations()
      const mappedMutations: PendingMutation[] = mutations.map((m) => ({
        id: m.id,
        type: 'api-call',
        description: `${m.method} ${m.endpoint}`,
        endpoint: m.endpoint,
        method: m.method,
        payload: m.payload,
        timestamp: m.timestamp,
        retryCount: m.retryCount,
        status: m.status,
        errorMessage: m.errorMessage,
      }))

      set({
        pendingMutations: mappedMutations,
        pendingCount: mappedMutations.length,
        isInitialized: true,
      })

      logger.info('[OfflineQueue] Initialisiert', { pendingCount: mappedMutations.length })
    } catch (error) {
      logger.error('[OfflineQueue] Initialisierung fehlgeschlagen', { error })
      set({ isInitialized: true }) // Mark as initialized to prevent retry loops
    }
  },

  addPendingMutation: async (mutation) => {
    try {
      const id = await addMutation({
        endpoint: mutation.endpoint,
        method: mutation.method,
        payload: mutation.payload,
        maxRetries: mutation.maxRetries ?? 3,
      })

      const newMutation: PendingMutation = {
        id,
        type: mutation.type,
        description: mutation.description,
        endpoint: mutation.endpoint,
        method: mutation.method,
        payload: mutation.payload,
        timestamp: Date.now(),
        retryCount: 0,
        status: 'pending',
      }

      set((state) => ({
        pendingMutations: [...state.pendingMutations, newMutation],
        pendingCount: state.pendingCount + 1,
      }))

      logger.info('[OfflineQueue] Mutation hinzugefügt', {
        id,
        type: mutation.type,
        endpoint: mutation.endpoint,
      })

      return id
    } catch (error) {
      logger.error('[OfflineQueue] Fehler beim Hinzufügen', { error })
      throw error
    }
  },

  removePendingMutation: async (id) => {
    try {
      await removeMutation(id)

      set((state) => {
        const filtered = state.pendingMutations.filter((m) => m.id !== id)
        return {
          pendingMutations: filtered,
          pendingCount: filtered.length,
        }
      })

      logger.info('[OfflineQueue] Mutation entfernt', { id })
    } catch (error) {
      logger.error('[OfflineQueue] Fehler beim Entfernen', { error })
      throw error
    }
  },

  updateMutationStatus: async (id, status, errorMessage) => {
    try {
      await updateMutationStatus(id, status, errorMessage)

      set((state) => ({
        pendingMutations: state.pendingMutations.map((m) =>
          m.id === id
            ? { ...m, status, errorMessage, retryCount: m.retryCount + 1 }
            : m
        ),
      }))
    } catch (error) {
      logger.error('[OfflineQueue] Fehler beim Status-Update', { error })
      throw error
    }
  },

  startSync: () => {
    set({ isSyncing: true })
    logger.info('[OfflineQueue] Sync gestartet')
  },

  finishSync: (success) => {
    set((state) => ({
      isSyncing: false,
      lastSyncedAt: success ? Date.now() : state.lastSyncedAt,
    }))
    logger.info('[OfflineQueue] Sync beendet', { success })
  },

  processQueue: async (processor) => {
    const { pendingMutations, startSync, finishSync, removePendingMutation, updateMutationStatus } = get()

    if (pendingMutations.length === 0) {
      return { success: 0, failed: 0 }
    }

    startSync()
    let success = 0
    let failed = 0

    for (const mutation of pendingMutations.filter((m) => m.status === 'pending')) {
      try {
        // Mark as processing
        await updateMutationStatus(mutation.id, 'processing')

        // Process the mutation
        const result = await processor(mutation)

        if (result) {
          // Success - remove from queue
          await removePendingMutation(mutation.id)
          success++
        } else {
          // Failed but retriable
          await updateMutationStatus(mutation.id, 'pending', 'Verarbeitung fehlgeschlagen')
          failed++
        }
      } catch (error) {
        // Error - mark as failed if max retries exceeded
        const maxRetries = 3
        if (mutation.retryCount >= maxRetries) {
          await updateMutationStatus(
            mutation.id,
            'failed',
            error instanceof Error ? error.message : 'Unbekannter Fehler'
          )
        } else {
          await updateMutationStatus(mutation.id, 'pending', 'Wird wiederholt...')
        }
        failed++
      }
    }

    finishSync(failed === 0)
    return { success, failed }
  },

  refresh: async () => {
    try {
      const mutations = await getPendingMutations()
      const mappedMutations: PendingMutation[] = mutations.map((m) => ({
        id: m.id,
        type: 'api-call',
        description: `${m.method} ${m.endpoint}`,
        endpoint: m.endpoint,
        method: m.method,
        payload: m.payload,
        timestamp: m.timestamp,
        retryCount: m.retryCount,
        status: m.status,
        errorMessage: m.errorMessage,
      }))

      set({
        pendingMutations: mappedMutations,
        pendingCount: mappedMutations.length,
      })
    } catch (error) {
      logger.error('[OfflineQueue] Refresh fehlgeschlagen', { error })
    }
  },

  clearPendingMutations: async () => {
    try {
      const { pendingMutations } = get()

      // Remove all from IndexedDB
      for (const mutation of pendingMutations) {
        await removeMutation(mutation.id)
      }

      set({
        pendingMutations: [],
        pendingCount: 0,
        lastSyncedAt: Date.now(),
      })

      logger.info('[OfflineQueue] Alle Mutationen gelöscht')
    } catch (error) {
      logger.error('[OfflineQueue] Fehler beim Löschen', { error })
      throw error
    }
  },

  reset: () => {
    set(initialState)
  },
}))

// ==================== Selectors ====================

/** Gibt true zurück wenn ausstehende Änderungen existieren */
export const selectHasPendingChanges = (state: OfflineQueueState) =>
  state.pendingCount > 0

/** Gibt die Anzahl der ausstehenden Änderungen zurück */
export const selectPendingCount = (state: OfflineQueueState) =>
  state.pendingCount

/** Gibt true zurück wenn Sync läuft */
export const selectIsSyncing = (state: OfflineQueueState) =>
  state.isSyncing

/** Gibt nur pending Mutationen zurück */
export const selectPendingMutations = (state: OfflineQueueState) =>
  state.pendingMutations.filter((m) => m.status === 'pending')

/** Gibt fehlgeschlagene Mutationen zurück */
export const selectFailedMutations = (state: OfflineQueueState) =>
  state.pendingMutations.filter((m) => m.status === 'failed')

// ==================== Helpers ====================

/**
 * Formatiert die Zeit seit dem letzten Sync
 */
export function formatTimeSinceSync(lastSyncedAt: number | null): string {
  if (!lastSyncedAt) return 'Noch nie synchronisiert'

  const now = Date.now()
  const diff = now - lastSyncedAt

  if (diff < 60000) return 'Gerade eben'
  if (diff < 3600000) return `Vor ${Math.floor(diff / 60000)} Minuten`
  if (diff < 86400000) return `Vor ${Math.floor(diff / 3600000)} Stunden`
  return `Vor ${Math.floor(diff / 86400000)} Tagen`
}

/**
 * Hook zum automatischen Initialisieren des Stores
 */
export function useInitializeOfflineQueue() {
  const initialize = useOfflineQueueStore((state) => state.initialize)
  const isInitialized = useOfflineQueueStore((state) => state.isInitialized)

  if (!isInitialized) {
    // Initialize on first access
    initialize()
  }
}

export default useOfflineQueueStore
