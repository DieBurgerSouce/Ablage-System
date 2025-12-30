/**
 * FormRegistryContext - Global Form Dirty State Management
 *
 * Ermoeglicht globale Verfolgung von unsaved changes ueber mehrere Formulare.
 * Integration mit TanStack Router fuer Navigation Blocking.
 *
 * @example
 * ```tsx
 * // In main.tsx
 * <FormRegistryProvider>
 *   <App />
 * </FormRegistryProvider>
 *
 * // In einer Form-Komponente
 * const { registerForm, unregisterForm, setDirty } = useFormRegistry();
 *
 * useEffect(() => {
 *   const formId = registerForm('employee-form');
 *   return () => unregisterForm(formId);
 * }, []);
 *
 * // Bei Aenderungen
 * setDirty(formId, true);
 * ```
 */

import {
    createContext,
    useContext,
    useCallback,
    useState,
    useEffect,
    useMemo,
    useRef,
    type ReactNode,
} from 'react';
import { useBlocker } from '@tanstack/react-router';

// ==================== Types ====================

interface FormState {
    id: string;
    name: string;
    isDirty: boolean;
    registeredAt: Date;
}

interface FormRegistryContextValue {
    /** Register a new form */
    registerForm: (name: string) => string;
    /** Unregister a form */
    unregisterForm: (id: string) => void;
    /** Set dirty state for a form */
    setDirty: (id: string, isDirty: boolean) => void;
    /** Check if any form is dirty */
    hasUnsavedChanges: boolean;
    /** Get all dirty forms */
    dirtyForms: FormState[];
    /** Get all registered forms */
    allForms: FormState[];
    /** Clear all forms (e.g., after navigation is confirmed) */
    clearAll: () => void;
}

// ==================== Context ====================

const FormRegistryContext = createContext<FormRegistryContextValue | null>(null);

// ==================== Hook ====================

export function useFormRegistry(): FormRegistryContextValue {
    const context = useContext(FormRegistryContext);
    if (!context) {
        throw new Error('useFormRegistry must be used within FormRegistryProvider');
    }
    return context;
}

/**
 * Hook fuer einzelne Formulare - vereinfachte API
 *
 * WICHTIG: Registriert das Formular bei Mount und entfernt es bei Unmount.
 * Verwendet useEffect fuer korrektes Cleanup (nicht useState!).
 *
 * ENTERPRISE FIX: Verwendet Refs um Callback-Referenzen zu stabilisieren.
 * Dies verhindert Memory Leaks durch unnoetige Effect-Re-Runs wenn
 * registerForm/unregisterForm sich bei Parent-Renders aendern.
 */
export function useFormDirtyTracking(formName: string) {
    const { registerForm, unregisterForm, setDirty } = useFormRegistry();
    const formIdRef = useRef<string | null>(null);

    // ENTERPRISE FIX: Stabilisiere Callback-Referenzen mit Refs
    // Dies verhindert dass der Effect bei jedem Parent-Render neu laeuft
    const registerFormRef = useRef(registerForm);
    const unregisterFormRef = useRef(unregisterForm);
    const setDirtyRef = useRef(setDirty);

    // Update refs bei jeder Aenderung (synchron, vor Effects)
    registerFormRef.current = registerForm;
    unregisterFormRef.current = unregisterForm;
    setDirtyRef.current = setDirty;

    // Register on mount, unregister on unmount
    // NUR formName als Dependency - Refs aendern sich nicht
    useEffect(() => {
        const id = registerFormRef.current(formName);
        formIdRef.current = id;

        return () => {
            if (formIdRef.current) {
                unregisterFormRef.current(formIdRef.current);
                formIdRef.current = null;
            }
        };
    }, [formName]); // NUR formName - keine Callback-Dependencies mehr

    const markDirty = useCallback(() => {
        if (formIdRef.current) {
            setDirtyRef.current(formIdRef.current, true);
        }
    }, []); // Keine Dependencies - verwendet Ref

    const markClean = useCallback(() => {
        if (formIdRef.current) {
            setDirtyRef.current(formIdRef.current, false);
        }
    }, []); // Keine Dependencies - verwendet Ref

    return {
        formId: formIdRef.current,
        markDirty,
        markClean,
    };
}

// ==================== Provider ====================

interface FormRegistryProviderProps {
    children: ReactNode;
    /** Custom message for unsaved changes dialog */
    warningMessage?: string;
}

// ==================== Constants ====================

/** Maximale Anzahl registrierter Formulare um Memory Leaks zu verhindern */
const MAX_FORMS = 100;

/** Zeit in ms nach der nicht-dirty Formulare als stale gelten */
const STALE_THRESHOLD_MS = 5 * 60 * 1000; // 5 Minuten

export function FormRegistryProvider({
    children,
    warningMessage = 'Sie haben ungespeicherte Aenderungen. Moechten Sie die Seite wirklich verlassen?',
}: FormRegistryProviderProps) {
    const [forms, setForms] = useState<Map<string, FormState>>(new Map());

    // Computed values
    const allForms = Array.from(forms.values());
    const dirtyForms = allForms.filter((f) => f.isDirty);
    const hasUnsavedChanges = dirtyForms.length > 0;

    // Block navigation when there are unsaved changes
    useBlocker({
        condition: hasUnsavedChanges,
    });

    // Register form mit Groessenlimit und Stale-Cleanup
    const registerForm = useCallback((name: string): string => {
        const id = `form-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        setForms((prev) => {
            const next = new Map(prev);
            const now = Date.now();

            // Cleanup: Entferne stale Eintraege (nicht-dirty und aelter als Threshold)
            // Dies verhindert Memory Leaks wenn unregisterForm nicht aufgerufen wird
            for (const [key, form] of next) {
                const age = now - form.registeredAt.getTime();
                if (!form.isDirty && age > STALE_THRESHOLD_MS) {
                    next.delete(key);
                }
            }

            // Enforce Limit: Warnung ausgeben wenn Limit erreicht
            if (next.size >= MAX_FORMS) {
                console.warn(
                    `[FormRegistry] Max Limit von ${MAX_FORMS} Formularen erreicht. ` +
                    `Aelteste nicht-dirty Eintraege werden entfernt.`
                );
                // Entferne aelteste nicht-dirty Eintraege bis Platz ist
                const sortedEntries = Array.from(next.entries())
                    .filter(([, form]) => !form.isDirty)
                    .sort((a, b) => a[1].registeredAt.getTime() - b[1].registeredAt.getTime());

                // Entferne bis zu 10 aelteste Eintraege oder bis genug Platz ist
                const toRemove = Math.min(10, sortedEntries.length);
                for (let i = 0; i < toRemove && next.size >= MAX_FORMS; i++) {
                    next.delete(sortedEntries[i][0]);
                }

                // Wenn immer noch voll (alle sind dirty), Warnung
                if (next.size >= MAX_FORMS) {
                    console.error(
                        '[FormRegistry] Kann neues Formular nicht registrieren - ' +
                        'alle bestehenden Formulare haben ungespeicherte Aenderungen.'
                    );
                    return prev;
                }
            }

            next.set(id, {
                id,
                name,
                isDirty: false,
                registeredAt: new Date(),
            });
            return next;
        });
        return id;
    }, []);

    // Unregister form
    const unregisterForm = useCallback((id: string) => {
        setForms((prev) => {
            const next = new Map(prev);
            next.delete(id);
            return next;
        });
    }, []);

    // Set dirty state
    const setDirty = useCallback((id: string, isDirty: boolean) => {
        setForms((prev) => {
            const form = prev.get(id);
            if (!form || form.isDirty === isDirty) return prev;

            const next = new Map(prev);
            next.set(id, { ...form, isDirty });
            return next;
        });
    }, []);

    // Clear all
    const clearAll = useCallback(() => {
        setForms(new Map());
    }, []);

    // Memoize context value to prevent unnecessary re-renders of consumers
    const value = useMemo<FormRegistryContextValue>(
        () => ({
            registerForm,
            unregisterForm,
            setDirty,
            hasUnsavedChanges,
            dirtyForms,
            allForms,
            clearAll,
        }),
        [registerForm, unregisterForm, setDirty, hasUnsavedChanges, dirtyForms, allForms, clearAll]
    );

    return (
        <FormRegistryContext.Provider value={value}>
            {children}
        </FormRegistryContext.Provider>
    );
}

// ==================== Global Navigation Guard ====================

/**
 * Hook fuer globale Navigation Guard
 * Zeigt automatisch Warning Dialog bei unsaved changes
 *
 * WICHTIG: Verwendet useEffect fuer korrektes Event-Listener-Cleanup.
 * Der hasUnsavedChanges-Wert wird via Ref aktualisiert, um stale closures zu vermeiden.
 */
export function useGlobalUnsavedChangesGuard() {
    const { hasUnsavedChanges, dirtyForms } = useFormRegistry();

    // Use ref to avoid stale closure in event handler
    const hasUnsavedChangesRef = useRef(hasUnsavedChanges);
    hasUnsavedChangesRef.current = hasUnsavedChanges;

    // Browser beforeunload - proper cleanup with useEffect
    useEffect(() => {
        const handler = (e: BeforeUnloadEvent) => {
            if (hasUnsavedChangesRef.current) {
                e.preventDefault();
                e.returnValue = '';
            }
        };

        window.addEventListener('beforeunload', handler);

        return () => {
            window.removeEventListener('beforeunload', handler);
        };
    }, []); // Empty deps - handler uses ref to get current value

    // Memoize message to prevent unnecessary recalculations
    const message = useMemo(() => {
        if (dirtyForms.length === 0) return undefined;
        return `Folgende Formulare haben ungespeicherte Änderungen: ${dirtyForms
            .map((f) => f.name)
            .join(', ')}`;
    }, [dirtyForms]);

    return {
        hasUnsavedChanges,
        dirtyForms,
        message,
    };
}

// ==================== Export ====================

export default FormRegistryProvider;
