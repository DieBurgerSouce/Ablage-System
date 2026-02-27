import { createFileRoute, redirect } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';
import { canAccessJobQueue } from '@/features/job-queue/hooks/use-job-permissions';
import { authService } from '@/lib/api/services/auth';

const JobQueueDashboard = lazy(() => import('@/features/job-queue/components/JobQueueDashboard').then(m => ({ default: m.JobQueueDashboard })));

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
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <JobQueueDashboard />
    </Suspense>
  );
}
