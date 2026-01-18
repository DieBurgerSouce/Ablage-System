/**
 * Sendungen Index Route
 *
 * Hauptseite für Sendungsverfolgung.
 * Zeigt Liste aller Sendungen mit Filter und Summary.
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { toast } from 'sonner';
import { Package } from 'lucide-react';
import {
  ShipmentList,
  useShipmentPage,
  useShipmentMutations,
  UI_LABELS,
} from '@/features/shipments';
import type { ShipmentFilter } from '@/features/shipments';

export const Route = createFileRoute('/sendungen/')({
  component: SendungenPage,
});

function SendungenPage() {
  const [filter, setFilter] = useState<Partial<ShipmentFilter>>({
    page: 1,
    perPage: 20,
  });

  const {
    shipments,
    pagination,
    summary,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useShipmentPage(filter);

  const { refreshTracking, refreshAll, deleteShipment } = useShipmentMutations();

  const handleRefresh = async (shipmentId: string) => {
    try {
      await refreshTracking.mutateAsync(shipmentId);
      toast.success(UI_LABELS.successRefresh);
    } catch {
      toast.error(UI_LABELS.errorRefresh);
    }
  };

  const handleRefreshAll = async () => {
    try {
      const result = await refreshAll.mutateAsync();
      toast.success(`${result.updated} Sendungen aktualisiert`);
      if (result.failed > 0) {
        toast.warning(`${result.failed} Sendungen konnten nicht aktualisiert werden`);
      }
    } catch {
      toast.error('Fehler beim Aktualisieren der Sendungen');
    }
  };

  const handleDelete = async (shipmentId: string) => {
    try {
      await deleteShipment.mutateAsync(shipmentId);
      toast.success(UI_LABELS.successDelete);
    } catch {
      toast.error(UI_LABELS.errorDelete);
    }
  };

  if (isError) {
    return (
      <div className="container mx-auto py-8">
        <div className="flex flex-col items-center justify-center gap-4 py-12">
          <Package className="h-16 w-16 text-muted-foreground opacity-50" />
          <h2 className="text-xl font-semibold text-destructive">
            {UI_LABELS.errorLoad}
          </h2>
          <p className="text-muted-foreground">
            {error instanceof Error ? error.message : 'Ein Fehler ist aufgetreten'}
          </p>
          <button
            onClick={() => refetch()}
            className="text-primary hover:underline"
          >
            Erneut versuchen
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8">
      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Package className="h-8 w-8 text-primary" />
          {UI_LABELS.pageTitle}
        </h1>
        <p className="text-muted-foreground mt-1">{UI_LABELS.pageSubtitle}</p>
      </div>

      {/* Shipment List */}
      <ShipmentList
        shipments={shipments}
        pagination={pagination}
        summary={summary}
        isLoading={isLoading}
        isFetching={isFetching}
        filter={filter}
        onFilterChange={setFilter}
        onRefresh={handleRefresh}
        onRefreshAll={handleRefreshAll}
        onDelete={handleDelete}
        isRefreshing={refreshTracking.isPending}
        isRefreshingAll={refreshAll.isPending}
      />
    </div>
  );
}
