/**
 * Hook für Feld-Navigation im Review-Workflow.
 *
 * Ermöglicht:
 * - Navigation mit J/K oder Tab/Shift+Tab
 * - Fokus-Tracking über data-Attribute
 * - Bestätigung des aktuell fokussierten Feldes
 */

import { useState, useCallback, useEffect, useRef } from 'react'

// Selektor für alle navigierbaren Felder
const FIELD_SELECTOR = '[data-field-nav]'

export interface UseFieldNavigationOptions {
    /** Container-Referenz für Feldsuche */
    containerRef: React.RefObject<HTMLElement>
    /** Callback wenn Feld fokussiert wird */
    onFieldFocus?: (fieldPath: string | null) => void
    /** Ob Navigation aktiv ist */
    enabled?: boolean
}

export interface UseFieldNavigationReturn {
    /** Aktuell fokussierter Feldpfad */
    currentField: string | null
    /** Index des aktuell fokussierten Feldes */
    currentIndex: number
    /** Gesamtanzahl navigierbarer Felder */
    totalFields: number
    /** Navigiere zum nächsten Feld */
    goToNext: () => void
    /** Navigiere zum vorherigen Feld */
    goToPrevious: () => void
    /** Fokussiere ein bestimmtes Feld */
    focusField: (fieldPath: string) => void
    /** Setze Fokus zurück */
    resetFocus: () => void
}

/**
 * Hook für Feld-Navigation.
 */
export function useFieldNavigation({
    containerRef,
    onFieldFocus,
    enabled = true,
}: UseFieldNavigationOptions): UseFieldNavigationReturn {
    const [currentIndex, setCurrentIndex] = useState(-1)
    const [currentField, setCurrentField] = useState<string | null>(null)
    const [totalFields, setTotalFields] = useState(0)

    // Ref für aktuelle Feld-Elemente
    const fieldsRef = useRef<HTMLElement[]>([])

    /**
     * Aktualisiert die Liste der Feld-Elemente.
     */
    const updateFields = useCallback(() => {
        if (!containerRef.current) return []

        const fields = Array.from(
            containerRef.current.querySelectorAll<HTMLElement>(FIELD_SELECTOR)
        )
        fieldsRef.current = fields
        setTotalFields(fields.length)
        return fields
    }, [containerRef])

    /**
     * Fokussiert ein Feld-Element und scrollt es in den Sichtbereich.
     */
    const focusElement = useCallback((element: HTMLElement, index: number) => {
        // Finde das fokussierbare Element (Input oder Button im Feld)
        const focusable = element.querySelector<HTMLElement>(
            'input, textarea, button, [tabindex="0"]'
        )

        if (focusable) {
            focusable.focus()
            // Scrolle Element in den Sichtbereich
            element.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        }

        const fieldPath = element.getAttribute('data-field-nav') || null
        setCurrentIndex(index)
        setCurrentField(fieldPath)
        onFieldFocus?.(fieldPath)
    }, [onFieldFocus])

    /**
     * Navigiere zum nächsten Feld.
     */
    const goToNext = useCallback(() => {
        if (!enabled) return

        const fields = updateFields()
        if (fields.length === 0) return

        const nextIndex = currentIndex < fields.length - 1 ? currentIndex + 1 : 0
        focusElement(fields[nextIndex], nextIndex)
    }, [enabled, currentIndex, updateFields, focusElement])

    /**
     * Navigiere zum vorherigen Feld.
     */
    const goToPrevious = useCallback(() => {
        if (!enabled) return

        const fields = updateFields()
        if (fields.length === 0) return

        const prevIndex = currentIndex > 0 ? currentIndex - 1 : fields.length - 1
        focusElement(fields[prevIndex], prevIndex)
    }, [enabled, currentIndex, updateFields, focusElement])

    /**
     * Fokussiere ein bestimmtes Feld über seinen Pfad.
     */
    const focusField = useCallback((fieldPath: string) => {
        if (!enabled) return

        const fields = updateFields()
        const index = fields.findIndex(f => f.getAttribute('data-field-nav') === fieldPath)

        if (index >= 0) {
            focusElement(fields[index], index)
        }
    }, [enabled, updateFields, focusElement])

    /**
     * Setze Fokus zurück.
     */
    const resetFocus = useCallback(() => {
        setCurrentIndex(-1)
        setCurrentField(null)
        onFieldFocus?.(null)
    }, [onFieldFocus])

    // Aktualisiere Feld-Liste bei Container-Änderungen
    useEffect(() => {
        if (!containerRef.current) return

        // Initiale Aktualisierung
        updateFields()

        // MutationObserver für dynamische Änderungen
        const observer = new MutationObserver(() => {
            updateFields()
        })

        observer.observe(containerRef.current, {
            childList: true,
            subtree: true,
        })

        return () => observer.disconnect()
    }, [containerRef, updateFields])

    // Event-Listener für native Tab-Navigation
    useEffect(() => {
        if (!enabled || !containerRef.current) return

        const handleFocusIn = (event: FocusEvent) => {
            const target = event.target as HTMLElement
            // Finde das nächste Eltern-Element mit data-field-nav
            const fieldElement = target.closest<HTMLElement>(FIELD_SELECTOR)

            if (fieldElement) {
                const fields = fieldsRef.current
                const index = fields.indexOf(fieldElement)

                if (index >= 0) {
                    const fieldPath = fieldElement.getAttribute('data-field-nav') || null
                    setCurrentIndex(index)
                    setCurrentField(fieldPath)
                    onFieldFocus?.(fieldPath)
                }
            }
        }

        containerRef.current.addEventListener('focusin', handleFocusIn)
        return () => {
            containerRef.current?.removeEventListener('focusin', handleFocusIn)
        }
    }, [enabled, containerRef, onFieldFocus])

    return {
        currentField,
        currentIndex,
        totalFields,
        goToNext,
        goToPrevious,
        focusField,
        resetFocus,
    }
}
