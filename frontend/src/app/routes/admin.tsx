import { createFileRoute, Outlet, useMatches } from '@tanstack/react-router'
import { UserManagement } from '@/features/admin/components/UserManagement'

export const Route = createFileRoute('/admin')({
    component: AdminLayout,
})

function AdminLayout() {
    const matches = useMatches()

    // Prüfe ob wir auf einer Child-Route sind (z.B. /admin/ocr-training)
    const isChildRoute = matches.some(match =>
        match.routeId !== '/admin' && match.routeId.startsWith('/admin/')
    )

    // Wenn Child-Route, nur Outlet rendern
    if (isChildRoute) {
        return <Outlet />
    }

    // Ansonsten die Admin-Hauptseite mit UserManagement
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">Administration</h1>
                <p className="text-muted-foreground mt-2">
                    Verwalten Sie Benutzer, Rollen und Systemeinstellungen.
                </p>
            </div>

            <UserManagement />
        </div>
    )
}
