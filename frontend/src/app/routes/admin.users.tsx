import { createFileRoute } from '@tanstack/react-router'
import { UserManagement } from '@/features/admin/components/UserManagement'

export const Route = createFileRoute('/admin/users')({
    component: UserManagementPage,
})

function UserManagementPage() {
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <UserManagement />
        </div>
    )
}
