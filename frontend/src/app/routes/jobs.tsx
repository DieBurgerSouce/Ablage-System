import { createFileRoute, redirect } from '@tanstack/react-router';

/**
 * Legacy /jobs route - redirects to /admin/job-queue
 *
 * Die alte Job Queue Route wurde durch das neue Enterprise-Level
 * Admin Dashboard ersetzt unter /admin/job-queue.
 */
export const Route = createFileRoute('/jobs')({
  beforeLoad: async () => {
    throw redirect({
      to: '/admin/job-queue',
      replace: true,
    });
  },
  component: () => null,
});
