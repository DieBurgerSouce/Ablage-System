/**
 * VehicleCreateDialog - Dialog zum Erstellen eines neuen Fahrzeugs
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
import type { PrivatVehicleCreate, VehicleType, FuelType } from '@/types/privat';

interface VehicleCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: PrivatVehicleCreate) => Promise<void>;
  isLoading?: boolean;
}

const VEHICLE_TYPES: { value: VehicleType; label: string }[] = [
  { value: 'car', label: 'PKW' },
  { value: 'motorcycle', label: 'Motorrad' },
  { value: 'truck', label: 'LKW' },
  { value: 'trailer', label: 'Anhänger' },
  { value: 'other', label: 'Sonstiges' },
];

const FUEL_TYPES: { value: FuelType; label: string }[] = [
  { value: 'petrol', label: 'Benzin' },
  { value: 'diesel', label: 'Diesel' },
  { value: 'electric', label: 'Elektro' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'lpg', label: 'Autogas (LPG)' },
  { value: 'other', label: 'Sonstiges' },
];

export function VehicleCreateDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: VehicleCreateDialogProps) {
  const [formData, setFormData] = React.useState<PrivatVehicleCreate>({
    name: '',
    vehicleType: 'car',
  });
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    try {
      await onSubmit({
        ...formData,
        name: formData.name.trim(),
        year: formData.year || undefined,
        purchasePrice: formData.purchasePrice || undefined,
        currentMileage: formData.currentMileage || undefined,
      });
      resetForm();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fehler beim Erstellen');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      vehicleType: 'car',
    });
    setError(null);
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      resetForm();
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Neues Fahrzeug</DialogTitle>
            <DialogDescription>
              Erfassen Sie ein neues Fahrzeug in Ihrem Portfolio.
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
                value={formData.name}
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
                value={formData.vehicleType}
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

            {/* Year & Fuel Type */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="year">Baujahr</Label>
                <Input
                  id="year"
                  type="number"
                  min={1900}
                  max={new Date().getFullYear() + 1}
                  value={formData.year || ''}
                  onChange={(e) => setFormData({ ...formData, year: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder={new Date().getFullYear().toString()}
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="fuelType">Kraftstoff</Label>
                <Select
                  value={formData.fuelType || ''}
                  onValueChange={(value) => setFormData({ ...formData, fuelType: value as FuelType })}
                  disabled={isLoading}
                >
                  <SelectTrigger id="fuelType">
                    <SelectValue placeholder="Auswählen" />
                  </SelectTrigger>
                  <SelectContent>
                    {FUEL_TYPES.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* License Plate & VIN */}
            <div className="grid grid-cols-2 gap-4">
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
              <div className="grid gap-2">
                <Label htmlFor="vin">FIN</Label>
                <Input
                  id="vin"
                  value={formData.vin || ''}
                  onChange={(e) => setFormData({ ...formData, vin: e.target.value.toUpperCase() })}
                  placeholder="Fahrzeug-ID"
                  maxLength={17}
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Purchase Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="purchaseDate">Kaufdatum</Label>
                <Input
                  id="purchaseDate"
                  type="date"
                  value={formData.purchaseDate || ''}
                  onChange={(e) => setFormData({ ...formData, purchaseDate: e.target.value })}
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="purchasePrice">Kaufpreis (€)</Label>
                <Input
                  id="purchasePrice"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.purchasePrice || ''}
                  onChange={(e) => setFormData({ ...formData, purchasePrice: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Current Mileage */}
            <div className="grid gap-2">
              <Label htmlFor="currentMileage">Aktueller Kilometerstand</Label>
              <Input
                id="currentMileage"
                type="number"
                min={0}
                value={formData.currentMileage || ''}
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
              Erstellen
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default VehicleCreateDialog;
