/**
 * Inventory Route
 *
 * Lagerverwaltung und Wareneingang
 */

import { createFileRoute } from '@tanstack/react-router';
import { InventoryPage } from '@/features/inventory';

export const Route = createFileRoute('/inventory')({
  component: InventoryRoute,
});

function InventoryRoute() {
  return (
    <div className="h-full">
      <InventoryPage />
    </div>
  );
}
