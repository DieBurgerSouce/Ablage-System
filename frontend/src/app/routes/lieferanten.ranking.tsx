/**
 * Supplier Ranking Route
 *
 * Route fuer das Lieferanten-Ranking Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { SupplierRankingDashboard } from '@/features/supplier-ranking';

export const Route = createFileRoute('/lieferanten/ranking')({
  component: SupplierRankingPage,
});

function SupplierRankingPage() {
  return (
    <div className="container mx-auto py-6 px-4">
      <SupplierRankingDashboard />
    </div>
  );
}
