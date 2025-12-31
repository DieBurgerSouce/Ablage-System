/**
 * VehiclesPage - Fahrzeuge-Übersicht
 *
 * Liste aller Fahrzeuge mit Verwaltungsfunktionen
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { VehicleList } from '../components/vehicles/VehicleList';
import * as privatApi from '../api/privat-api';
import type { PrivatVehicleWithStats } from '@/types/privat';
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

export function VehiclesPage() {
  const navigate = useNavigate();
  const { spaceId } = useParams({ strict: false }) as { spaceId?: string };

  const [vehicles, setVehicles] = React.useState<PrivatVehicleWithStats[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(0);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [deleteVehicle, setDeleteVehicle] = React.useState<PrivatVehicleWithStats | null>(null);

  const pageSize = 12;

  // Load vehicles
  React.useEffect(() => {
    const loadVehicles = async () => {
      if (!spaceId) {
        setError(new Error('Kein Bereich ausgewählt'));
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
  }, [spaceId, page, searchQuery]);

  const handleSelectVehicle = (vehicle: PrivatVehicleWithStats) => {
    navigate({
      to: '/privat/fahrzeuge/$vehicleId' as string,
      params: { vehicleId: vehicle.id },
    } as never);
  };

  const handleCreateVehicle = () => {
    // TODO: Open create vehicle dialog/form
    toast.info('Fahrzeug-Formular wird implementiert');
  };

  const handleEditVehicle = (vehicle: PrivatVehicleWithStats) => {
    // TODO: Open edit vehicle dialog/form
    toast.info('Fahrzeug-Formular wird implementiert');
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
    </div>
  );
}

export default VehiclesPage;
