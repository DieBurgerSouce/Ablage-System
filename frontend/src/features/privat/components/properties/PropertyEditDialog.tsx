/**
 * PropertyEditDialog - Dialog zum Bearbeiten einer Immobilie
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
import type { PrivatPropertyUpdate, PrivatPropertyWithDetails } from '@/types/privat';

interface PropertyEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  property: PrivatPropertyWithDetails | null;
  onSubmit: (propertyId: string, data: PrivatPropertyUpdate) => Promise<void>;
  isLoading?: boolean;
}

const PROPERTY_TYPES = [
  { value: 'apartment', label: 'Wohnung' },
  { value: 'house', label: 'Haus' },
  { value: 'commercial', label: 'Gewerbe' },
  { value: 'land', label: 'Grundstück' },
  { value: 'garage', label: 'Garage/Stellplatz' },
  { value: 'other', label: 'Sonstiges' },
];

export function PropertyEditDialog({
  open,
  onOpenChange,
  property,
  onSubmit,
  isLoading = false,
}: PropertyEditDialogProps) {
  const [formData, setFormData] = React.useState<PrivatPropertyUpdate>({});
  const [error, setError] = React.useState<string | null>(null);

  // Initialize form data when property changes
  React.useEffect(() => {
    if (property) {
      setFormData({
        name: property.name,
        propertyType: property.propertyType,
        addressStreet: property.addressStreet,
        addressCity: property.addressCity,
        addressZip: property.addressZip,
        addressCountry: property.addressCountry,
        currentValue: property.currentValue,
        sizeSqm: property.sizeSqm,
        rooms: property.rooms,
        notes: property.notes,
      });
    }
  }, [property]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!property) return;

    if (formData.name && !formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    try {
      await onSubmit(property.id, {
        ...formData,
        name: formData.name?.trim(),
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

  if (!property) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Immobilie bearbeiten</DialogTitle>
            <DialogDescription>
              Ändern Sie die Details Ihrer Immobilie.
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
                placeholder="z.B. Meine Eigentumswohnung"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Property Type */}
            <div className="grid gap-2">
              <Label htmlFor="propertyType">Immobilientyp</Label>
              <Select
                value={formData.propertyType || ''}
                onValueChange={(value) => setFormData({ ...formData, propertyType: value })}
                disabled={isLoading}
              >
                <SelectTrigger id="propertyType">
                  <SelectValue placeholder="Typ auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {PROPERTY_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Address */}
            <div className="grid gap-2">
              <Label>Adresse</Label>
              <Input
                value={formData.addressStreet || ''}
                onChange={(e) => setFormData({ ...formData, addressStreet: e.target.value })}
                placeholder="Straße und Hausnummer"
                disabled={isLoading}
              />
              <div className="grid grid-cols-3 gap-2">
                <Input
                  value={formData.addressZip || ''}
                  onChange={(e) => setFormData({ ...formData, addressZip: e.target.value })}
                  placeholder="PLZ"
                  maxLength={10}
                  disabled={isLoading}
                />
                <Input
                  className="col-span-2"
                  value={formData.addressCity || ''}
                  onChange={(e) => setFormData({ ...formData, addressCity: e.target.value })}
                  placeholder="Stadt"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Current Value & Size */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="currentValue">Aktueller Wert (€)</Label>
                <Input
                  id="currentValue"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.currentValue ?? ''}
                  onChange={(e) => setFormData({ ...formData, currentValue: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="sizeSqm">Fläche (m²)</Label>
                <Input
                  id="sizeSqm"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.sizeSqm ?? ''}
                  onChange={(e) => setFormData({ ...formData, sizeSqm: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Rooms */}
            <div className="grid gap-2">
              <Label htmlFor="rooms">Zimmeranzahl</Label>
              <Input
                id="rooms"
                type="number"
                min={0}
                step={0.5}
                value={formData.rooms ?? ''}
                onChange={(e) => setFormData({ ...formData, rooms: e.target.value ? Number(e.target.value) : undefined })}
                placeholder="z.B. 3.5"
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

export default PropertyEditDialog;
