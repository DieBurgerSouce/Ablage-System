import { createFileRoute } from '@tanstack/react-router';
import { TrustDashboardPage } from '@/features/trust-dashboard/components/TrustDashboardPage';

export const Route = createFileRoute('/trust-dashboard')({
  component: TrustDashboardPageRoute,
});

function TrustDashboardPageRoute() {
  return (
    <div className="p-8 space-y-8">
      <TrustDashboardPage />
    </div>
  );
}
