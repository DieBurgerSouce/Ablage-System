import { createFileRoute } from '@tanstack/react-router';
import { SystemHealthOverview } from '@/features/admin/components/system-health';

export const Route = createFileRoute('/admin/system-health')({
    component: SystemHealthPage,
});

function SystemHealthPage() {
    return <SystemHealthOverview />;
}
