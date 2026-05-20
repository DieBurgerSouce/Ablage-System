/**
 * useViewerShortcuts - Keyboard-Shortcuts für den Dokument-Viewer
 *
 * Unterstützt:
 * - Ctrl + +/-/0: Zoom (vergrößern, verkleinern, zurücksetzen)
 * - Alt + Left/Right: Seiten-Navigation
 * - Page Up/Down: Seiten-Navigation
 * - Home/End: Erste/Letzte Seite
 */

import { useEffect, useCallback } from 'react';

interface UseViewerShortcutsOptions {
    /** Aktueller Zoom-Faktor */
    scale: number;
    /** Callback zum Setzen des Zoom-Faktors */
    onScaleChange: (scale: number) => void;
    /** Aktuelle Seite (1-basiert) */
    currentPage?: number;
    /** Anzahl der Seiten */
    numPages?: number | null;
    /** Callback zum Setzen der aktuellen Seite */
    onPageChange?: (page: number) => void;
    /** Minimaler Zoom-Faktor */
    minScale?: number;
    /** Maximaler Zoom-Faktor */
    maxScale?: number;
    /** Zoom-Schrittweite */
    scaleStep?: number;
    /** Deaktiviert den Hook */
    disabled?: boolean;
}

export function useViewerShortcuts({
    scale,
    onScaleChange,
    currentPage = 1,
    numPages = null,
    onPageChange,
    minScale = 0.25,
    maxScale = 4,
    scaleStep = 0.25,
    disabled = false,
}: UseViewerShortcutsOptions) {
    const zoomIn = useCallback(() => {
        onScaleChange(Math.min(scale + scaleStep, maxScale));
    }, [scale, onScaleChange, scaleStep, maxScale]);

    const zoomOut = useCallback(() => {
        onScaleChange(Math.max(scale - scaleStep, minScale));
    }, [scale, onScaleChange, scaleStep, minScale]);

    const resetZoom = useCallback(() => {
        onScaleChange(1);
    }, [onScaleChange]);

    const goToPreviousPage = useCallback(() => {
        if (onPageChange && currentPage > 1) {
            onPageChange(currentPage - 1);
        }
    }, [onPageChange, currentPage]);

    const goToNextPage = useCallback(() => {
        if (onPageChange && numPages && currentPage < numPages) {
            onPageChange(currentPage + 1);
        }
    }, [onPageChange, currentPage, numPages]);

    const goToFirstPage = useCallback(() => {
        if (onPageChange) {
            onPageChange(1);
        }
    }, [onPageChange]);

    const goToLastPage = useCallback(() => {
        if (onPageChange && numPages) {
            onPageChange(numPages);
        }
    }, [onPageChange, numPages]);

    useEffect(() => {
        if (disabled) return;

        const handleKeyDown = (event: KeyboardEvent) => {
            // Ignoriere Ereignisse wenn Fokus auf Input/Textarea
            const target = event.target as HTMLElement;
            if (
                target.tagName === 'INPUT' ||
                target.tagName === 'TEXTAREA' ||
                target.isContentEditable
            ) {
                return;
            }

            const isCtrl = event.ctrlKey || event.metaKey;
            const isAlt = event.altKey;

            // Zoom: Ctrl + +/-/0
            if (isCtrl && !isAlt) {
                switch (event.key) {
                    case '+':
                    case '=': // = ist auf deutschen Tastaturen die + Taste ohne Shift
                        event.preventDefault();
                        zoomIn();
                        return;
                    case '-':
                        event.preventDefault();
                        zoomOut();
                        return;
                    case '0':
                        event.preventDefault();
                        resetZoom();
                        return;
                }
            }

            // Seiten-Navigation: Alt + Left/Right
            if (isAlt && !isCtrl) {
                switch (event.key) {
                    case 'ArrowLeft':
                        event.preventDefault();
                        goToPreviousPage();
                        return;
                    case 'ArrowRight':
                        event.preventDefault();
                        goToNextPage();
                        return;
                }
            }

            // Page Up/Down für Seiten-Navigation
            if (!isCtrl && !isAlt) {
                switch (event.key) {
                    case 'PageUp':
                        event.preventDefault();
                        goToPreviousPage();
                        return;
                    case 'PageDown':
                        event.preventDefault();
                        goToNextPage();
                        return;
                    case 'Home':
                        event.preventDefault();
                        goToFirstPage();
                        return;
                    case 'End':
                        event.preventDefault();
                        goToLastPage();
                        return;
                }
            }
        };

        window.addEventListener('keydown', handleKeyDown);

        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [
        disabled,
        zoomIn,
        zoomOut,
        resetZoom,
        goToPreviousPage,
        goToNextPage,
        goToFirstPage,
        goToLastPage,
    ]);

    // Rückgabe der Funktionen für programmatische Nutzung
    return {
        zoomIn,
        zoomOut,
        resetZoom,
        goToPreviousPage,
        goToNextPage,
        goToFirstPage,
        goToLastPage,
    };
}
