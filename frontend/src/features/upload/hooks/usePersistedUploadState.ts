import { useState, useEffect, useCallback, useRef } from 'react';
import type { UploadingFile, TransactionGroup } from '../types';

const STORAGE_PREFIX = 'upload-session-';
const HARD_RELOAD_FLAG = 'upload-hard-reload-requested';

/**
 * Custom Hook für persistierten State in sessionStorage.
 * Überlebt normale Page-Reloads, wird bei Hard-Reload (Ctrl+Shift+R) zurückgesetzt.
 */
export function usePersistedUploadState<T>(
    key: string,
    initialValue: T,
    options?: {
        deserialize?: (data: unknown) => T;
        serialize?: (data: T) => unknown;
    }
): [T, React.Dispatch<React.SetStateAction<T>>, () => void] {
    const storageKey = STORAGE_PREFIX + key;
    const isInitialized = useRef(false);

    // Memoize options to prevent unnecessary effect runs
    const serializeRef = useRef(options?.serialize);
    const deserializeRef = useRef(options?.deserialize);
    serializeRef.current = options?.serialize;
    deserializeRef.current = options?.deserialize;

    // Initialize state from sessionStorage or use initial value
    const [state, setState] = useState<T>(() => {
        // Check for hard reload flag first
        try {
            if (sessionStorage.getItem(HARD_RELOAD_FLAG) === 'true') {
                // Clear all upload-related storage
                const keysToRemove: string[] = [];
                for (let i = 0; i < sessionStorage.length; i++) {
                    const k = sessionStorage.key(i);
                    if (k?.startsWith(STORAGE_PREFIX)) {
                        keysToRemove.push(k);
                    }
                }
                keysToRemove.forEach(k => sessionStorage.removeItem(k));
                sessionStorage.removeItem(HARD_RELOAD_FLAG);
                return initialValue;
            }
        } catch {
            // sessionStorage not available
        }

        // Try to restore from sessionStorage
        try {
            const stored = sessionStorage.getItem(storageKey);
            if (stored) {
                const parsed = JSON.parse(stored);
                const deserialize = deserializeRef.current;
                return deserialize ? deserialize(parsed) : parsed;
            }
        } catch {
            // Parse error or sessionStorage not available
        }
        return initialValue;
    });

    // Persist to sessionStorage on every state change
    useEffect(() => {
        // Skip the initial effect to avoid unnecessary writes
        if (!isInitialized.current) {
            isInitialized.current = true;
            return;
        }

        try {
            const serialize = serializeRef.current;
            const dataToStore = serialize ? serialize(state) : state;
            sessionStorage.setItem(storageKey, JSON.stringify(dataToStore));
        } catch {
            // sessionStorage not available or quota exceeded
        }
    }, [storageKey, state]); // Removed options from dependencies!

    // Clear function to manually reset state
    const clearState = useCallback(() => {
        try {
            sessionStorage.removeItem(storageKey);
        } catch {
            // Ignore
        }
        setState(initialValue);
    }, [storageKey, initialValue]);

    return [state, setState, clearState];
}

/**
 * Setzt Clear-Flag wenn Ctrl+R gedrückt wird.
 * Bei Ctrl+R wird der Upload-State beim nächsten Load gelöscht.
 * Muss einmal beim App-Start aufgerufen werden.
 */
export function setupHardReloadDetection(): () => void {
    const handleKeydown = (e: KeyboardEvent): void => {
        // Ctrl+R (ohne Shift) - löscht den Upload-State
        const isClearReload = e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'r';

        if (isClearReload) {
            try {
                sessionStorage.setItem(HARD_RELOAD_FLAG, 'true');
            } catch {
                // Ignore
            }
        }
    };

    window.addEventListener('keydown', handleKeydown);

    // Return cleanup function
    return () => {
        window.removeEventListener('keydown', handleKeydown);
    };
}

/**
 * Deserialisiert UploadingFile-Array aus sessionStorage.
 * File-Objekte können nicht serialisiert werden, daher werden nur
 * bereits hochgeladene Dateien (mit documentId) wiederhergestellt.
 */
export function deserializeFiles(data: unknown): UploadingFile[] {
    if (!Array.isArray(data)) return [];

    return data
        // Nur Dateien mit documentId (bereits hochgeladen) wiederherstellen
        .filter((f): f is Record<string, unknown> =>
            typeof f === 'object' && f !== null && 'documentId' in f && f.documentId
        )
        .map(f => ({
            id: String(f.id || ''),
            file: null, // File-Objekt kann nicht wiederhergestellt werden
            originalFilename: f.originalFilename as string | undefined,
            status: (f.status as UploadingFile['status']) || 'awaiting_confirmation',
            progress: typeof f.progress === 'number' ? f.progress : 100,
            error: f.error as string | undefined,
            documentId: String(f.documentId),
            taskId: f.taskId as string | undefined,
            ocrProgress: typeof f.ocrProgress === 'number' ? f.ocrProgress : undefined,
            ocrMessage: f.ocrMessage as string | undefined,
            classification: f.classification as UploadingFile['classification'],
            confirmedDirection: f.confirmedDirection as UploadingFile['confirmedDirection'],
            renameConfirmed: f.renameConfirmed as boolean | undefined,
            renamedFilename: f.renamedFilename as string | undefined,
            transactionGroupId: f.transactionGroupId as string | undefined,
        }));
}

/**
 * Serialisiert UploadingFile-Array für sessionStorage.
 * Entfernt das File-Objekt und filtert nicht-persistierbare Dateien.
 */
export function serializeFiles(files: UploadingFile[]): unknown[] {
    return files
        // Nur Dateien mit documentId persistieren
        .filter(f => f.documentId)
        .map(({ file, ...rest }) => rest); // File-Objekt entfernen
}

/**
 * Deserialisiert TransactionGroup-Array aus sessionStorage.
 */
export function deserializeGroups(data: unknown): TransactionGroup[] {
    if (!Array.isArray(data)) return [];

    return data
        .filter((g): g is Record<string, unknown> =>
            typeof g === 'object' && g !== null && 'id' in g
        )
        .map(g => ({
            id: String(g.id || ''),
            name: String(g.name || ''),
            documentIds: Array.isArray(g.documentIds)
                ? g.documentIds.map(String)
                : [],
            backendGroupId: g.backendGroupId as string | undefined,
            entityName: g.entityName as string | undefined,
            entityId: g.entityId as string | undefined,
            createdAt: g.createdAt ? new Date(g.createdAt as string) : new Date(),
            suggestedGroupName: g.suggestedGroupName as string | undefined,
            suggestedGroupNameApplied: g.suggestedGroupNameApplied as boolean | undefined,
        }));
}

/**
 * Serialisiert TransactionGroup-Array für sessionStorage.
 */
export function serializeGroups(groups: TransactionGroup[]): unknown[] {
    return groups.map(g => ({
        ...g,
        createdAt: g.createdAt.toISOString(),
    }));
}

/**
 * Löscht alle Upload-Session-Daten aus sessionStorage.
 */
export function clearAllUploadSessionData(): void {
    try {
        const keysToRemove: string[] = [];
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            if (key?.startsWith(STORAGE_PREFIX)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(k => sessionStorage.removeItem(k));
    } catch {
        // Ignore
    }
}
