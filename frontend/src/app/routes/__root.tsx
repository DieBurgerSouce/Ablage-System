import { useEffect, useState } from 'react'
import { createRootRoute, Outlet, useLocation, Navigate } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/router-devtools'
import { AnimatePresence, motion } from 'framer-motion'
import { AppLayout } from '@/components/layout/AppLayout'
import { useAuth } from '@/lib/auth/AuthContext'
import { SessionExpiredModal } from '@/components/auth/SessionExpiredModal'
import { Toaster } from '@/components/ui/toaster'
import { OfflineIndicator } from '@/components/OfflineIndicator'
import { OfflineSyncStatusBar } from '@/components/layout/OfflineSyncStatusBar'
import { WelcomeModal } from '@/components/onboarding/WelcomeModal'
// P4.1: Enhanced Onboarding Wizard (5-step first-login experience)
import { OnboardingWizard } from '@/features/onboarding'
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
// Feature 9: WebSocket-Verbindung automatisch bei Login herstellen
import { useWebSocketInit } from '@/lib/hooks/use-websocket-init'
// WCAG 2.1 AA: Skip Links for keyboard navigation
import { SkipLinks } from '@/components/SkipLinks'
// Phase 6: Session resume tracking + page transitions
import { pageTransition } from '@/lib/animations'
import { useSessionResume } from '@/hooks/use-session-resume'
// Phase 7.1: KI-Chat Assistent (RAG slide-out panel)
import { ChatPanel } from '@/features/ki-chat'
import { Bot } from 'lucide-react'

export const Route = createRootRoute({
    component: RootComponent,
})

function RootComponent() {
    const { isAuthenticated, isLoading } = useAuth()
    const location = useLocation()
    const { recordVisit } = useSessionResume()
    const [kiChatOpen, setKiChatOpen] = useState(false)

    // Feature 9: WebSocket-Verbindung automatisch bei Auth herstellen
    useWebSocketInit()

    // Phase 6: Track route visits for session resume
    useEffect(() => {
        recordVisit(location.pathname)
    }, [location.pathname, recordVisit])

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
                        <OfflineSyncStatusBar />
                        <GlobalCommandDialog />
                        <OfflineIndicator />
                        <AppLayout id="main-content">
                            <AnimatePresence mode="wait">
                                <motion.div key={location.pathname} {...pageTransition}>
                                    <Outlet />
                                </motion.div>
                            </AnimatePresence>
                            {import.meta.env.DEV && <TanStackRouterDevtools />}
                        </AppLayout>
                        <OnboardingWizard />
                        <WelcomeModal />
                        <SessionExpiredModal />
                        <Toaster />
                        <NotificationToastProvider />
                        {/* Phase 7.1: KI-Chat Assistent (RAG slide-out) */}
                        <KiChatFab onClick={() => setKiChatOpen(true)} />
                        <ChatPanel open={kiChatOpen} onOpenChange={setKiChatOpen} />
                    </GlobalShortcutsProvider>
                </TourProvider>
            </UndoProvider>
        </ErrorBoundary>
    )
}

function KiChatFab({ onClick }: { onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            className="fixed bottom-6 right-6 z-50 h-12 w-12 rounded-full bg-primary text-primary-foreground shadow-lg hover:bg-primary/90 flex items-center justify-center transition-transform hover:scale-105"
            aria-label="KI-Assistent oeffnen"
        >
            <Bot className="h-5 w-5" />
        </button>
    )
}
