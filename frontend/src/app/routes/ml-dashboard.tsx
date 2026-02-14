/**
 * ML Dashboard Route
 *
 * Dashboard für Machine Learning Performance und Lernfortschritt.
 */

import { createFileRoute } from '@tanstack/react-router';
import { MLDashboardPage } from '@/features/ml-dashboard';

export const Route = createFileRoute('/ml-dashboard')({
    component: MLDashboardPage,
});
