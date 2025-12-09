import { createFileRoute } from '@tanstack/react-router'
import { TuneManagement } from '@/features/admin/components/TuneManagement'

export const Route = createFileRoute('/admin/tunes')({
    component: TuneManagementPage,
})

function TuneManagementPage() {
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <TuneManagement />
        </div>
    )
}
