import { createFileRoute } from '@tanstack/react-router'
import { JobQueueDashboard } from '@/features/jobs/components/JobQueueDashboard'

export const Route = createFileRoute('/jobs')({
    component: JobsPage,
})

function JobsPage() {
    return (
        <div className="max-w-5xl mx-auto p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Job Queue</h1>
                <p className="text-muted-foreground mt-2">
                    Überwachen Sie den Status Ihrer OCR-Verarbeitungsaufträge.
                </p>
            </div>

            <JobQueueDashboard />
        </div>
    )
}
