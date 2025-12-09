import { createRootRoute, Outlet, useLocation, Navigate } from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/router-devtools'
import { AppLayout } from '@/components/layout/AppLayout'
import { useAuth } from '@/lib/auth/AuthContext'

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
    if (location.pathname === '/login') {
        return (
            <>
                <Outlet />
                <TanStackRouterDevtools />
            </>
        )
    }

    // Protect all other routes
    if (!isAuthenticated) {
        return <Navigate to="/login" />
    }

    // Render protected layout
    return (
        <AppLayout>
            <Outlet />
            <TanStackRouterDevtools />
        </AppLayout>
    )
}
