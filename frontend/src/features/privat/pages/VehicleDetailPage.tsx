/**
 * VehicleDetailPage - Fahrzeug-Detailansicht
 *
 * Zeigt alle Details eines Fahrzeugs inkl. Tankhistorie und Statistiken
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { ArrowLeft, Edit, Trash2, Car, Fuel, Gauge, Calendar, Loader2, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
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
import * as privatApi from '../api/privat-api';
import type { PrivatVehicleWithStats, PrivatVehicleUpdate, PrivatFuelLog, PrivatFuelStatistics } from '@/types/privat';
import { VehicleEditDialog } from '../components/vehicles/VehicleEditDialog';

const VEHICLE_TYPE_LABELS: Record<string, string> = {
  car: 'PKW',
  motorcycle: 'Motorrad',
  truck: 'LKW',
  trailer: 'Anhänger',
  other: 'Sonstiges',
};

const FUEL_TYPE_LABELS: Record<string, string> = {
  petrol: 'Benzin',
  diesel: 'Diesel',
  electric: 'Elektro',
  hybrid: 'Hybrid',
  lpg: 'LPG',
  other: 'Sonstiges',
};

export function VehicleDetailPage() {
  const navigate = useNavigate();
  const { vehicleId } = useParams({ strict: false }) as { vehicleId: string };

  const [vehicle, setVehicle] = React.useState<PrivatVehicleWithStats | null>(null);
  const [fuelLogs, setFuelLogs] = React.useState<PrivatFuelLog[]>([]);
  const [fuelStats, setFuelStats] = React.useState<PrivatFuelStatistics | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false);
  const [showEditDialog, setShowEditDialog] = React.useState(false);
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Load vehicle details
  React.useEffect(() => {
    const loadVehicle = async () => {
      if (!vehicleId) {
        setError(new Error('Keine Fahrzeug-ID angegeben'));
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const [vehicleData, logsData, statsData] = await Promise.all([
          privatApi.getVehicle(vehicleId),
          privatApi.listFuelLogs(vehicleId).catch(() => []),
          privatApi.getFuelStatistics(vehicleId).catch(() => null),
        ]);
        setVehicle(vehicleData);
        setFuelLogs(logsData);
        setFuelStats(statsData);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden des Fahrzeugs'));
      } finally {
        setIsLoading(false);
      }
    };
    loadVehicle();
  }, [vehicleId]);

  const handleEdit = async (vehId: string, data: PrivatVehicleUpdate) => {
    setIsUpdating(true);
    try {
      const updated = await privatApi.updateVehicle(vehId, data);
      setVehicle(updated);
      toast.success('Fahrzeug aktualisiert');
    } catch (err) {
      toast.error('Fehler beim Aktualisieren');
      throw err;
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!vehicle) return;

    try {
      await privatApi.deleteVehicle(vehicle.id);
      toast.success('Fahrzeug gelöscht');
      navigate({ to: '/privat/fahrzeuge' });
    } catch (err) {
      toast.error('Fehler beim Löschen des Fahrzeugs');
    } finally {
      setShowDeleteDialog(false);
    }
  };

  const handleBack = () => {
    navigate({ to: '/privat/fahrzeuge' });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !vehicle) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <p className="text-destructive mb-4">{error?.message || 'Fahrzeug nicht gefunden'}</p>
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{vehicle.name}</h1>
            <p className="text-muted-foreground">
              {[vehicle.brand, vehicle.model].filter(Boolean).join(' ') || VEHICLE_TYPE_LABELS[vehicle.vehicleType] || vehicle.vehicleType}
            </p>
          </div>
          {vehicle.licensePlate && (
            <Badge variant="outline" className="ml-2 font-mono">
              {vehicle.licensePlate}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowEditDialog(true)}>
            <Edit className="mr-2 h-4 w-4" />
            Bearbeiten
          </Button>
          <Button variant="destructive" onClick={() => setShowDeleteDialog(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            Löschen
          </Button>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Basic Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Car className="h-5 w-5" />
              Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Typ</span>
              <span>{VEHICLE_TYPE_LABELS[vehicle.vehicleType] || vehicle.vehicleType}</span>
            </div>
            {vehicle.brand && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Marke</span>
                <span>{vehicle.brand}</span>
              </div>
            )}
            {vehicle.model && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Modell</span>
                <span>{vehicle.model}</span>
              </div>
            )}
            {vehicle.year && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Baujahr</span>
                <span>{vehicle.year}</span>
              </div>
            )}
            {vehicle.fuelType && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kraftstoff</span>
                <span>{FUEL_TYPE_LABELS[vehicle.fuelType] || vehicle.fuelType}</span>
              </div>
            )}
            {vehicle.vin && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">FIN</span>
                <span className="font-mono text-xs">{vehicle.vin}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Mileage Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gauge className="h-5 w-5" />
              Kilometerstand
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {vehicle.currentMileage !== undefined && vehicle.currentMileage !== null && (
              <div className="text-center py-4">
                <p className="text-3xl font-bold">{vehicle.currentMileage.toLocaleString('de-DE')} km</p>
                <p className="text-sm text-muted-foreground">Aktueller Stand</p>
              </div>
            )}
            {vehicle.purchaseDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kaufdatum</span>
                <span>{new Date(vehicle.purchaseDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
            {vehicle.purchasePrice !== undefined && vehicle.purchasePrice !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kaufpreis</span>
                <span>{vehicle.purchasePrice.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Fuel Statistics Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Fuel className="h-5 w-5" />
              Verbrauch
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {fuelStats ? (
              <>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Durchschnittsverbrauch</span>
                  <span className="font-medium">{fuelStats.averageConsumption.toFixed(1)} L/100km</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Kosten/km</span>
                  <span>{fuelStats.costPerKm.toFixed(2)} €</span>
                </div>
                <Separator />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Getankt gesamt</span>
                  <span>{fuelStats.totalLiters.toFixed(0)} L</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Gesamtkosten</span>
                  <span>{fuelStats.totalCost.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-4">
                Keine Tankdaten vorhanden
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Fuel Log History */}
      {fuelLogs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Tankhistorie
            </CardTitle>
            <CardDescription>Die letzten Tankvorgänge</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {fuelLogs.slice(0, 10).map((log) => (
                <div key={log.id} className="flex items-center justify-between p-3 rounded-lg border">
                  <div>
                    <p className="font-medium">
                      {log.liters.toFixed(1)} L @ {log.pricePerLiter.toFixed(2)} €/L
                      {log.isFullTank && <Badge variant="outline" className="ml-2">Voll</Badge>}
                    </p>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {new Date(log.date).toLocaleDateString('de-DE')}
                      </span>
                      <span>{log.mileage.toLocaleString('de-DE')} km</span>
                      {log.station && <span>{log.station}</span>}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-medium">{log.totalCost.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Notes Section */}
      {vehicle.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notizen</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{vehicle.notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Edit Dialog */}
      <VehicleEditDialog
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        vehicle={vehicle}
        onSubmit={handleEdit}
        isLoading={isUpdating}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Fahrzeug löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie das Fahrzeug "{vehicle.name}" wirklich löschen?
              Alle zugehörigen Tankdaten und Dokumente werden ebenfalls gelöscht.
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
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

export default VehicleDetailPage;
