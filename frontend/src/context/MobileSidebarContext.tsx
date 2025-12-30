/**
 * MobileSidebarContext - Mobile Sidebar State Management
 *
 * Verwaltet den Zustand der mobilen Sidebar:
 * - isOpen: Ob die Sidebar auf Mobile sichtbar ist
 * - toggle: Umschalten der Sidebar-Sichtbarkeit
 * - close: Sidebar schließen (z.B. nach Navigation)
 *
 * Wird nur auf Mobile (<768px) verwendet - auf Desktop ist Sidebar immer sichtbar.
 */

import { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import type { ReactNode } from 'react';

// ==================== Types ====================

interface MobileSidebarContextType {
    /** Ob die Sidebar auf Mobile geoeffnet ist */
    isOpen: boolean;
    /** Sidebar oeffnen/schliessen umschalten */
    toggle: () => void;
    /** Sidebar schliessen */
    close: () => void;
    /** Sidebar oeffnen */
    open: () => void;
}

const MobileSidebarContext = createContext<MobileSidebarContextType | undefined>(undefined);

// ==================== Provider ====================

interface MobileSidebarProviderProps {
    children: ReactNode;
}

export function MobileSidebarProvider({ children }: MobileSidebarProviderProps) {
    const [isOpen, setIsOpen] = useState(false);

    // Schliesse Sidebar bei Resize auf Desktop
    useEffect(() => {
        const handleResize = () => {
            // Schliesse Sidebar wenn Viewport > 768px (md breakpoint)
            if (window.innerWidth >= 768) {
                setIsOpen(false);
            }
        };

        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    // Verhindere Body-Scroll wenn Sidebar offen ist
    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }

        return () => {
            document.body.style.overflow = '';
        };
    }, [isOpen]);

    const toggle = useCallback(() => {
        setIsOpen((prev) => !prev);
    }, []);

    const close = useCallback(() => {
        setIsOpen(false);
    }, []);

    const open = useCallback(() => {
        setIsOpen(true);
    }, []);

    const value = useMemo<MobileSidebarContextType>(
        () => ({
            isOpen,
            toggle,
            close,
            open,
        }),
        [isOpen, toggle, close, open]
    );

    return (
        <MobileSidebarContext.Provider value={value}>
            {children}
        </MobileSidebarContext.Provider>
    );
}

// ==================== Hook ====================

/**
 * Hook to access mobile sidebar context
 */
export function useMobileSidebar(): MobileSidebarContextType {
    const context = useContext(MobileSidebarContext);
    if (context === undefined) {
        throw new Error('useMobileSidebar must be used within a MobileSidebarProvider');
    }
    return context;
}

/**
 * Hook that safely returns mobile sidebar context (or undefined if not in provider)
 * Useful for components that may or may not be inside the provider
 */
export function useMobileSidebarSafe(): MobileSidebarContextType | null {
    const context = useContext(MobileSidebarContext);
    return context ?? null;
}
