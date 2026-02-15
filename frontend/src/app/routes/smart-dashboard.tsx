// Smart Dashboard Route
// Route: /smart-dashboard

import { createFileRoute } from '@tanstack/react-router';
import { SmartDashboardPage } from '@/features/smart-dashboard';

export const Route = createFileRoute('/smart-dashboard')({
  component: SmartDashboardPage,
});
