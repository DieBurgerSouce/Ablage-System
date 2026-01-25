/**
 * Banking Auto-Mahnlauf Route
 * Route fuer automatischen Mahnlauf Dashboard
 */

import { createFileRoute } from '@tanstack/react-router';
import { AutoMahnlaufDashboard } from '@/features/banking/components';

export const Route = createFileRoute('/banking/auto-mahnlauf')({
  component: AutoMahnlaufPage,
});

function AutoMahnlaufPage() {
  return <AutoMahnlaufDashboard />;
}
