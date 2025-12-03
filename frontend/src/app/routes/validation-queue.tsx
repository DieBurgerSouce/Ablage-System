import { createFileRoute } from '@tanstack/react-router'
import { ValidationDashboard } from '@/features/validation/components/ValidationDashboard'

export const Route = createFileRoute('/validation-queue')({
    component: ValidationQueuePage,
})

function ValidationQueuePage() {
    return (
        <div className="p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Validierungswarteschlange</h1>
                <p className="text-muted-foreground mt-2">
                    Überprüfen und korrigieren Sie Dokumente mit niedriger Konfidenz.
                </p>
            </div>
            <ValidationDashboard />
        </div>
    )
}
