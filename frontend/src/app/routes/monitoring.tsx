import { createFileRoute } from '@tanstack/react-router'
import { GPUMonitoringDashboard } from '@/features/monitoring/components/GPUMonitoringDashboard'

export const Route = createFileRoute('/monitoring')({
    component: MonitoringPage,
})

function MonitoringPage() {
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">System Monitoring</h1>
                <p className="text-muted-foreground mt-2">
                    Echtzeit-Überwachung der GPU-Auslastung und Systemressourcen.
                </p>
            </div>

            <GPUMonitoringDashboard />
        </div>
    )
}
