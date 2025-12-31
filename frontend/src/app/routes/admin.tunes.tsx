import { createFileRoute } from '@tanstack/react-router'
import { TuneManagement } from '@/features/admin/components/TuneManagement'

export const Route = createFileRoute('/admin/tunes')({
    component: TuneManagementPage,
})

function TuneManagementPage() {
    return (
        <div className="space-y-8">
            <TuneManagement />
        </div>
    )
}
