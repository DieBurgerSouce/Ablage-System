import { createRootRoute, Outlet, useLocation, Navigate } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/router-devtools'
import { AppLayout } from '@/components/layout/AppLayout'
import { useAuth } from '@/lib/auth/AuthContext'
import { SessionExpiredModal } from '@/components/auth/SessionExpiredModal'
import { Toaster } from '@/components/ui/toaster'
import { OfflineIndicator } from '@/components/OfflineIndicator'
import { WelcomeModal } from '@/components/onboarding/WelcomeModal'
// Feature 12: Guided Product Tours
import { TourProvider } from '@/features/product-tour'
import { GlobalShortcutsProvider } from '@/components/GlobalShortcutsProvider'
import { GlobalCommandDialog } from '@/components/GlobalCommandDialog'
// FIX Phase 7.5: ErrorBoundary für alle Routes (Enterprise Error Recovery)
import { ErrorBoundary } from '@/components/ErrorBoundary'
// Phase 4.4: Global Undo Provider for reversible actions
import { UndoProvider } from '@/hooks/useUndoableAction'
// Phase C: Echtzeit-Benachrichtigungen via WebSocket
import { NotificationToastProvider } from '@/features/notifications/components/NotificationToastProvider'
// WCAG 2.1 AA: Skip Links for keyboard navigation
import { SkipLinks } from '@/components/SkipLinks'

export const Route = createRootRoute({
    component: RootComponent,
})

function RootComponent() {
    const { isAuthenticated, isLoading } = useAuth()
    const location = useLocation()

    // Show loading state while checking auth
    if (isLoading) {
        return <div className="flex h-screen items-center justify-center">Wird geladen...</div>
    }

    // Public routes that don't need auth or layout
    // FIX Phase 7.5: ErrorBoundary um Auth-Routes (verhindert Blank Screen bei Fehlern)
    if (location.pathname === '/login' || location.pathname === '/forgot-password' || location.pathname.startsWith('/reset-password')) {
        return (
            <ErrorBoundary
                errorTitle="Anmeldefehler"
                errorDescription="Bei der Anmeldung ist ein Fehler aufgetreten. Bitte laden Sie die Seite neu."
            >
                <OfflineIndicator />
                <Outlet />
                <Toaster />
                {import.meta.env.DEV && <TanStackRouterDevtools />}
            </ErrorBoundary>
        )
    }

    // Protect all other routes
    if (!isAuthenticated) {
        return <Navigate to="/login" />
    }

    // Render protected layout
    // FIX Phase 7.5: ErrorBoundary um geschützte Routes (Enterprise Error Recovery)
    // Phase 4.4: UndoProvider für globale Undo-Funktionalität
    return (
        <ErrorBoundary
            errorTitle="Anwendungsfehler"
            errorDescription="Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es erneut oder kehren Sie zur Startseite zurück."
        >
            <UndoProvider options={{ maxStackSize: 30, toastDuration: 6000 }}>
                <TourProvider>
                    <GlobalShortcutsProvider>
                        <SkipLinks />
                        <GlobalCommandDialog />
                        <OfflineIndicator />
                        <AppLayout id="main-content">
                            <Outlet />
                            {import.meta.env.DEV && <TanStackRouterDevtools />}
                        </AppLayout>
                        <WelcomeModal />
                        <SessionExpiredModal />
                        <Toaster />
                        <NotificationToastProvider />
                    </GlobalShortcutsProvider>
                </TourProvider>
            </UndoProvider>
        </ErrorBoundary>
    )
}
