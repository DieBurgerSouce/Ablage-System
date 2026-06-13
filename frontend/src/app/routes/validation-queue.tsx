import { createFileRoute, redirect } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'
import { authService } from '@/lib/api/services/auth'

const ValidationQueueDashboard = lazyRoute(() => import('@/features/validation/components/ValidationQueueDashboard').then(m => ({ default: m.ValidationQueueDashboard })))

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
        <div className="p-8">
            <ValidationQueueDashboard />
        </div>
    )
}
