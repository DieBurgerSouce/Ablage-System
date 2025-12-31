import { createFileRoute, redirect } from '@tanstack/react-router';
import { JobQueueDashboard } from '@/features/job-queue/components/JobQueueDashboard';
import { canAccessJobQueue } from '@/features/job-queue/hooks/use-job-permissions';
import { authService } from '@/lib/api/services/auth';

export const Route = createFileRoute('/admin/job-queue')({
  beforeLoad: async () => {
    // Check if user has permission to access job queue
    const user = authService.getCurrentUser();
    if (!canAccessJobQueue(user)) {
      throw redirect({
        to: '/admin',
        replace: true,
      });
    }
  },
  component: JobQueuePage,
});

function JobQueuePage() {
  return <JobQueueDashboard />;
}
