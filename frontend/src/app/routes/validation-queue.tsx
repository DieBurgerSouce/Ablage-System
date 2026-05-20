import { createFileRoute, redirect } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'
import { authService } from '@/lib/api/services/auth'

const ValidationQueueDashboard = lazy(() => import('@/features/validation/components/ValidationQueueDashboard').then(m => ({ default: m.ValidationQueueDashboard })))

export const Route = createFileRoute('/validation-queue')({
    beforeLoad: async () => {
        // Permission-Check: Nur editor oder admin dürfen die Validierungsseite sehen
        const user = authService.getCurrentUser()
        if (!user) {
            throw redirect({ to: '/login' })
        }
        const hasAccess = user.is_superuser || user.role === 'admin' || user.role === 'editor'
        if (!hasAccess) {
            throw redirect({ to: '/' })
        }
    },
    component: ValidationQueuePage,
})

function ValidationQueuePage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <div className="p-8">
                <ValidationQueueDashboard />
            </div>
        </Suspense>
    )
}
