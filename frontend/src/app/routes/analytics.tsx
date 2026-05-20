// Analytics Route
// Route: /analytics

import { createFileRoute } from '@tanstack/react-router';
import { AnalyticsPage } from '@/features/analytics';

export const Route = createFileRoute('/analytics')({
  component: AnalyticsPage,
});
