import { createFileRoute } from '@tanstack/react-router';
import { CeoDashboardPage } from '@/features/ceo-dashboard';

export const Route = createFileRoute('/dashboard/ceo')({
  component: CeoDashboardRoute,
});

function CeoDashboardRoute() {
  return <CeoDashboardPage />;
}
