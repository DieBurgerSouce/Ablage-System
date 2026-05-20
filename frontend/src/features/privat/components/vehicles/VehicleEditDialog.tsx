/**
 * VehicleEditDialog - Dialog zum Bearbeiten eines Fahrzeugs
 */

import * as React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import type { PrivatVehicleUpdate, PrivatVehicleWithStats, VehicleType } from '@/types/privat';

interface VehicleEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  vehicle: PrivatVehicleWithStats | null;
  onSubmit: (vehicleId: string, data: PrivatVehicleUpdate) => Promise<void>;
  isLoading?: boolean;
}

const VEHICLE_TYPES: { value: VehicleType; label: string }[] = [
  { value: 'car', label: 'PKW' },
  { value: 'motorcycle', label: 'Motorrad' },
  { value: 'truck', label: 'LKW' },
  { value: 'trailer', label: 'Anhänger' },
  { value: 'other', label: 'Sonstiges' },
];

export function VehicleEditDialog({
  open,
  onOpenChange,
  vehicle,
  onSubmit,
  isLoading = false,
}: VehicleEditDialogProps) {
  const [formData, setFormData] = React.useState<PrivatVehicleUpdate>({});
  const [error, setError] = React.useState<string | null>(null);

  // Initialize form data when vehicle changes
  React.useEffect(() => {
    if (vehicle) {
      setFormData({
        name: vehicle.name,
        vehicleType: vehicle.vehicleType,
        brand: vehicle.brand,
        model: vehicle.model,
        licensePlate: vehicle.licensePlate,
        currentMileage: vehicle.currentMileage,
        notes: vehicle.notes,
      });
    }
  }, [vehicle]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!vehicle) return;

    if (formData.name && !formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    try {
      await onSubmit(vehicle.id, {
        ...formData,
        name: formData.name?.trim(),
        licensePlate: formData.licensePlate?.toUpperCase(),
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Speichern');
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setError(null);
    }
    onOpenChange(newOpen);
  };

  if (!vehicle) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Fahrzeug bearbeiten</DialogTitle>
            <DialogDescription>
              Ändern Sie die Details Ihres Fahrzeugs.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Name */}
            <div className="grid gap-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                value={formData.name || ''}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="z.B. Familienauto"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Vehicle Type */}
            <div className="grid gap-2">
              <Label htmlFor="vehicleType">Fahrzeugtyp</Label>
              <Select
                value={formData.vehicleType || ''}
                onValueChange={(value) => setFormData({ ...formData, vehicleType: value as VehicleType })}
                disabled={isLoading}
              >
                <SelectTrigger id="vehicleType">
                  <SelectValue placeholder="Typ auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {VEHICLE_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Brand & Model */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="brand">Marke</Label>
                <Input
                  id="brand"
                  value={formData.brand || ''}
                  onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                  placeholder="z.B. BMW"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="model">Modell</Label>
                <Input
                  id="model"
                  value={formData.model || ''}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  placeholder="z.B. 320d"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* License Plate */}
            <div className="grid gap-2">
              <Label htmlFor="licensePlate">Kennzeichen</Label>
              <Input
                id="licensePlate"
                value={formData.licensePlate || ''}
                onChange={(e) => setFormData({ ...formData, licensePlate: e.target.value.toUpperCase() })}
                placeholder="z.B. B-AB 1234"
                disabled={isLoading}
              />
            </div>

            {/* Current Mileage */}
            <div className="grid gap-2">
              <Label htmlFor="currentMileage">Aktueller Kilometerstand</Label>
              <Input
                id="currentMileage"
                type="number"
                min={0}
                value={formData.currentMileage ?? ''}
                onChange={(e) => setFormData({ ...formData, currentMileage: e.target.value ? Number(e.target.value) : undefined })}
                placeholder="0"
                disabled={isLoading}
              />
            </div>

            {/* Notes */}
            <div className="grid gap-2">
              <Label htmlFor="notes">Notizen</Label>
              <Textarea
                id="notes"
                value={formData.notes || ''}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Optionale Notizen..."
                rows={2}
                maxLength={1000}
                disabled={isLoading}
              />
            </div>

            {/* Error */}
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isLoading}
            >
              Abbrechen
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default VehicleEditDialog;
