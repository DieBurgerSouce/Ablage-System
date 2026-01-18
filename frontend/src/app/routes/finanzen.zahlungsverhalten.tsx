/**
 * Payment Behavior Route
 *
 * Route fuer Zahlungsverhaltens-Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PaymentBehaviorDashboard } from '@/features/payment-behavior';

export const Route = createFileRoute('/finanzen/zahlungsverhalten')({
  component: PaymentBehaviorPage,
});

function PaymentBehaviorPage() {
  return (
    <div className="container mx-auto py-6 px-4">
      <PaymentBehaviorDashboard />
    </div>
  );
}
