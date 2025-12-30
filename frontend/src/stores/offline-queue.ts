/**
 * Offline Queue Store
 *
 * Zustand-Store zum Verfolgen von ausstehenden Aenderungen
 * die synchronisiert werden muessen, wenn wieder online.
 *
 * Features:
 * - Zaehlt ausstehende Mutationen
 * - Verfolgt Sync-Status
 * - Integration mit TanStack Query Mutations
 */

import { create } from 'zustand';

// ==================== Types ====================

interface PendingMutation {
  id: string;
  type: string;
  description: string;
  timestamp: number;
}

interface OfflineQueueState {
  /** Ausstehende Aenderungen */
  pendingMutations: PendingMutation[];

  /** Sync in progress */
  isSyncing: boolean;

  /** Letzter erfolgreicher Sync-Zeitpunkt */
  lastSyncedAt: number | null;

  /** Anzahl der ausstehenden Aenderungen */
  pendingCount: number;
}

interface OfflineQueueActions {
  /** Fuegt eine ausstehende Mutation hinzu */
  addPendingMutation: (mutation: Omit<PendingMutation, 'id' | 'timestamp'>) => void;

  /** Entfernt eine Mutation nach erfolgreichem Sync */
  removePendingMutation: (id: string) => void;

  /** Markiert Sync als gestartet */
  startSync: () => void;

  /** Markiert Sync als beendet */
  finishSync: (success: boolean) => void;

  /** Loescht alle ausstehenden Mutationen (z.B. nach erfolgreichem Sync) */
  clearPendingMutations: () => void;

  /** Setzt den Store zurueck */
  reset: () => void;
}

type OfflineQueueStore = OfflineQueueState & OfflineQueueActions;

// ==================== Initial State ====================

const initialState: OfflineQueueState = {
  pendingMutations: [],
  isSyncing: false,
  lastSyncedAt: null,
  pendingCount: 0,
};

// ==================== Store ====================

export const useOfflineQueueStore = create<OfflineQueueStore>((set, get) => ({
  ...initialState,

  addPendingMutation: (mutation) => {
    const id = `mutation-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const newMutation: PendingMutation = {
      ...mutation,
      id,
      timestamp: Date.now(),
    };

    set((state) => ({
      pendingMutations: [...state.pendingMutations, newMutation],
      pendingCount: state.pendingMutations.length + 1,
    }));
  },

  removePendingMutation: (id) => {
    set((state) => {
      const filtered = state.pendingMutations.filter((m) => m.id !== id);
      return {
        pendingMutations: filtered,
        pendingCount: filtered.length,
      };
    });
  },

  startSync: () => {
    set({ isSyncing: true });
  },

  finishSync: (success) => {
    set((state) => ({
      isSyncing: false,
      lastSyncedAt: success ? Date.now() : state.lastSyncedAt,
    }));
  },

  clearPendingMutations: () => {
    set({
      pendingMutations: [],
      pendingCount: 0,
      lastSyncedAt: Date.now(),
    });
  },

  reset: () => {
    set(initialState);
  },
}));

// ==================== Selectors ====================

/** Gibt true zurueck wenn ausstehende Aenderungen existieren */
export const selectHasPendingChanges = (state: OfflineQueueState) =>
  state.pendingCount > 0;

/** Gibt die Anzahl der ausstehenden Aenderungen zurueck */
export const selectPendingCount = (state: OfflineQueueState) =>
  state.pendingCount;

/** Gibt true zurueck wenn Sync laeuft */
export const selectIsSyncing = (state: OfflineQueueState) =>
  state.isSyncing;

// ==================== Helpers ====================

/**
 * Formatiert die Zeit seit dem letzten Sync
 */
export function formatTimeSinceSync(lastSyncedAt: number | null): string {
  if (!lastSyncedAt) return 'Noch nie synchronisiert';

  const now = Date.now();
  const diff = now - lastSyncedAt;

  if (diff < 60000) return 'Gerade eben';
  if (diff < 3600000) return `Vor ${Math.floor(diff / 60000)} Minuten`;
  if (diff < 86400000) return `Vor ${Math.floor(diff / 3600000)} Stunden`;
  return `Vor ${Math.floor(diff / 86400000)} Tagen`;
}

export default useOfflineQueueStore;
