/**
 * Sendung Detail Route
 *
 * Detailansicht einer einzelnen Sendung mit Timeline.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { toast } from 'sonner';
import { Package } from 'lucide-react';
import {
  ShipmentDetail,
  useShipment,
  useRefreshTracking,
  useDeleteShipment,
  UI_LABELS,
} from '@/features/shipments';

export const Route = createFileRoute('/sendungen/$shipmentId')({
  component: SendungDetailPage,
});

function SendungDetailPage() {
  const { shipmentId } = Route.useParams();
  const navigate = useNavigate();

  const {
    data: shipment,
    isLoading,
    isError,
    error,
    refetch,
  } = useShipment(shipmentId);

  const refreshTracking = useRefreshTracking();
  const deleteShipment = useDeleteShipment();

  const handleRefresh = async () => {
    try {
      await refreshTracking.mutateAsync(shipmentId);
      toast.success(UI_LABELS.successRefresh);
    } catch {
      toast.error(UI_LABELS.errorRefresh);
    }
  };

  const handleDelete = async () => {
    try {
      await deleteShipment.mutateAsync(shipmentId);
      toast.success(UI_LABELS.successDelete);
      navigate({ to: '/sendungen' });
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
            Sendung nicht gefunden
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

  if (isLoading || !shipment) {
    return (
      <div className="container mx-auto py-8">
        <ShipmentDetail
          shipment={{} as never}
          isLoading={true}
        />
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8">
      <ShipmentDetail
        shipment={shipment}
        onRefresh={handleRefresh}
        onDelete={handleDelete}
        isRefreshing={refreshTracking.isPending}
      />
    </div>
  );
}
