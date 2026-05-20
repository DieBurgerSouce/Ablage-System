import { createFileRoute, redirect } from '@tanstack/react-router'
import { ValidationQueueEditor } from '@/features/validation/components/ValidationQueueEditor'
import { authService } from '@/lib/api/services/auth'

export const Route = createFileRoute('/validation-queue/$id')({
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
    component: ValidationItemPage,
})

function ValidationItemPage() {
    const { id } = Route.useParams()

    return (
        <div className="h-screen flex flex-col">
            <ValidationQueueEditor itemId={id} />
        </div>
    )
}
