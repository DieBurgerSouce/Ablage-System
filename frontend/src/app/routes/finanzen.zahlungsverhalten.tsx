/**
 * Payment Behavior Route
 *
 * Route für Zahlungsverhaltens-Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { PaymentBehaviorDashboard } from '@/features/payment-behavior';

export const Route = createFileRoute('/finanzen/zahlungsverhalten')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts);
  // die /finanzen-Dokumentablage selbst bleibt aktiv (Archiv-Kern).
  beforeLoad: () => frozenModuleGuard('finance'),
  component: PaymentBehaviorPage,
});

function PaymentBehaviorPage() {
  return (
    <div className="container mx-auto py-6 px-4">
      <PaymentBehaviorDashboard />
    </div>
  );
}
