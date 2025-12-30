import { createRootRoute, Outlet, useLocation, Navigate } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/router-devtools'
import { AppLayout } from '@/components/layout/AppLayout'
import { useAuth } from '@/lib/auth/AuthContext'
import { SessionExpiredModal } from '@/components/auth/SessionExpiredModal'
import { Toaster } from '@/components/ui/toaster'
import { OfflineIndicator } from '@/components/OfflineIndicator'
import { WelcomeModal } from '@/components/onboarding/WelcomeModal'
import { GlobalShortcutsProvider } from '@/components/GlobalShortcutsProvider'

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
    if (location.pathname === '/login' || location.pathname === '/forgot-password' || location.pathname.startsWith('/reset-password')) {
        return (
            <>
                <OfflineIndicator />
                <Outlet />
                <Toaster />
                {import.meta.env.DEV && <TanStackRouterDevtools />}
            </>
        )
    }

    // Protect all other routes
    if (!isAuthenticated) {
        return <Navigate to="/login" />
    }

    // Render protected layout
    return (
        <GlobalShortcutsProvider>
            <OfflineIndicator />
            <AppLayout>
                <Outlet />
                {import.meta.env.DEV && <TanStackRouterDevtools />}
            </AppLayout>
            <WelcomeModal />
            <SessionExpiredModal />
            <Toaster />
        </GlobalShortcutsProvider>
    )
}
