/**
 * Fraud Detection Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { FraudDashboard } from '@/features/fraud';

export const Route = createFileRoute('/fraud')({
  component: FraudPage,
});

function FraudPage() {
  return <FraudDashboard />;
}
