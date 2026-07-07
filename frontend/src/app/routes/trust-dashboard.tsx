import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { TrustDashboardPage } from '@/features/trust-dashboard/components/TrustDashboardPage';

export const Route = createFileRoute('/trust-dashboard')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: TrustDashboardPageRoute,
});

function TrustDashboardPageRoute() {
  return (
    <div className="p-8 space-y-8">
      <TrustDashboardPage />
    </div>
  );
}
