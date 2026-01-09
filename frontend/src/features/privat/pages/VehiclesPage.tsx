/**
 * VehiclesPage - Fahrzeuge-Übersicht
 *
 * Liste aller Fahrzeuge mit Verwaltungsfunktionen
 */

import * as React from 'react';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { VehicleList } from '../components/vehicles/VehicleList';
import { VehicleCreateDialog } from '../components/vehicles/VehicleCreateDialog';
import { VehicleEditDialog } from '../components/vehicles/VehicleEditDialog';
import * as privatApi from '../api/privat-api';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import type { PrivatVehicleWithStats, PrivatVehicleCreate, PrivatVehicleUpdate } from '@/types/privat';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';

interface VehiclesPageProps {
  spaceId?: string;
}

export function VehiclesPage({ spaceId: propSpaceId }: VehiclesPageProps = {}) {
  const navigate = useNavigate();
  const params = useParams({ strict: false }) as { spaceId?: string };
  const search = useSearch({ strict: false }) as { space?: string };
  const { defaultSpaceId, isLoading: isLoadingSpaces, hasSpaces } = useDefaultSpace();

  // Priorität: 1. Props, 2. URL-Params, 3. Query-Param (?space=), 4. Default-Space
  const spaceId = propSpaceId || params.spaceId || search.space || defaultSpaceId;

  const [vehicles, setVehicles] = React.useState<PrivatVehicleWithStats[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteVehicle, setDeleteVehicle] = React.useState<PrivatVehicleWithStats | null>(null);

  // Dialog state
  const [showCreateDialog, setShowCreateDialog] = React.useState(false);
  const [editVehicle, setEditVehicle] = React.useState<PrivatVehicleWithStats | null>(null);
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const pageSize = 12;

  // Load vehicles
  React.useEffect(() => {
    const loadVehicles = async () => {
      // Warte auf Spaces wenn noch keine spaceId vorhanden
      if (isLoadingSpaces && !spaceId) {
        return;
      }

      if (!spaceId) {
        if (!hasSpaces) {
          setError(new Error('Noch keine Bereiche vorhanden. Erstellen Sie zuerst einen persönlichen Bereich.'));
        } else {
          setError(new Error('Kein Bereich ausgewählt'));
        }
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const response = await privatApi.listVehicles(spaceId, {
          page: page + 1,
          pageSize,
          search: searchQuery || undefined,
        });
        setVehicles(response.items);
        setTotal(response.total);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setIsLoading(false);
      }
    };
    loadVehicles();
  }, [spaceId, page, searchQuery, isLoadingSpaces, hasSpaces]);

  const handleSelectVehicle = (vehicle: PrivatVehicleWithStats) => {
    void navigate({
      to: `/privat/fahrzeuge/${vehicle.id}`,
    });
  };

  const handleCreateVehicle = () => {
    setShowCreateDialog(true);
  };

  const handleEditVehicle = (vehicle: PrivatVehicleWithStats) => {
    setEditVehicle(vehicle);
  };

  const handleCreateSubmit = async (data: PrivatVehicleCreate) => {
    if (!spaceId) return;
    setIsSubmitting(true);
    try {
      const newVehicle = await privatApi.createVehicle(spaceId, data);
      setVehicles((prev) => [newVehicle, ...prev]);
      setTotal((prev) => prev + 1);
      toast.success('Fahrzeug erstellt');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (vehicleId: string, data: PrivatVehicleUpdate) => {
    setIsSubmitting(true);
    try {
      const updated = await privatApi.updateVehicle(vehicleId, data);
      setVehicles((prev) => prev.map((v) => (v.id === vehicleId ? updated : v)));
      toast.success('Fahrzeug aktualisiert');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteVehicle || !spaceId) return;

    try {
      await privatApi.deleteVehicle(deleteVehicle.id);
      setVehicles((prev) => prev.filter((v) => v.id !== deleteVehicle.id));
      setTotal((prev) => prev - 1);
      toast.success('Fahrzeug gelöscht');
    } catch (err) {
      toast.error('Fehler beim Löschen des Fahrzeugs');
    } finally {
      setDeleteVehicle(null);
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(0);
  };

  return (
    <div className="p-8">
      <VehicleList
        vehicles={vehicles}
        total={total}
        page={page}
        pageSize={pageSize}
        isLoading={isLoading}
        error={error}
        onPageChange={setPage}
        onSelect={handleSelectVehicle}
        onCreate={handleCreateVehicle}
        onEdit={handleEditVehicle}
        onDelete={setDeleteVehicle}
        onSearch={handleSearch}
        searchQuery={searchQuery}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteVehicle} onOpenChange={(open) => !open && setDeleteVehicle(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Fahrzeug löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie das Fahrzeug "{deleteVehicle?.name}" wirklich löschen?
              Alle Tankbelege werden ebenfalls gelöscht.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Create Dialog */}
      <VehicleCreateDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        onSubmit={handleCreateSubmit}
        isLoading={isSubmitting}
      />

      {/* Edit Dialog */}
      <VehicleEditDialog
        open={!!editVehicle}
        onOpenChange={(open) => !open && setEditVehicle(null)}
        vehicle={editVehicle}
        onSubmit={handleEditSubmit}
        isLoading={isSubmitting}
      />
    </div>
  );
}

export default VehiclesPage;
