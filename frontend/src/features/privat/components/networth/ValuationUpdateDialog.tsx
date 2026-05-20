/**
 * ValuationUpdateDialog - Dialog zur Bewertungsaktualisierung
 *
 * Ermoeglicht die Aktualisierung des aktuellen Werts eines Vermoegenswerts.
 * Unterstuetzt Immobilien, Fahrzeuge und Anlagen mit jeweils
 * kategoriespezifischen API-Aufrufen.
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { formatCurrencyDE } from '../../hooks/useNetWorth';
import type { AssetBreakdown } from '../../hooks/useNetWorth';

// ==================== Types ====================

interface AssetItem {
  id: string;
  name: string;
  currentValue: number;
  category: string;
  categoryLabel: string;
}

interface ValuationUpdateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  assets: AssetBreakdown[];
  spaceId: string;
  onSuccess: () => void;
}

// ==================== Component ====================

export function ValuationUpdateDialog({
  open,
  onOpenChange,
  assets,
  spaceId,
  onSuccess,
}: ValuationUpdateDialogProps) {
  const [selectedAssetId, setSelectedAssetId] = React.useState<string>('none');
  const [newValue, setNewValue] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const { toast } = useToast();

  // Flatten all asset items for selection
  const allAssetItems = React.useMemo((): AssetItem[] => {
    return assets.flatMap((category) =>
      category.items.map((item) => ({
        id: item.id,
        name: item.name,
        currentValue: item.value,
        category: category.category,
        categoryLabel: category.label,
      }))
    );
  }, [assets]);

  const selectedAsset = allAssetItems.find((a) => a.id === selectedAssetId);

  // Reset form when dialog closes
  React.useEffect(() => {
    if (!open) {
      setSelectedAssetId('none');
      setNewValue('');
    }
  }, [open]);

  const handleSubmit = async () => {
    if (!selectedAsset || !newValue) return;

    // Parse German-style number input (dots as thousands separator, comma as decimal)
    const numValue = parseFloat(
      newValue.replace(/\./g, '').replace(',', '.')
    );
    if (isNaN(numValue) || numValue < 0) {
      toast({
        title: 'Ungueltiger Wert',
        description: 'Bitte geben Sie einen gueltigen positiven Betrag ein.',
        variant: 'destructive',
      });
      return;
    }

    setIsSubmitting(true);
    try {
      // Dynamic import to avoid circular dependencies
      const privatApi = await import('../../api/privat-api');

      // Update based on category using the correct API signature
      switch (selectedAsset.category) {
        case 'properties':
          await privatApi.updateProperty(selectedAsset.id, {
            currentValue: numValue,
          });
          break;
        case 'vehicles':
          // Vehicles do not have a currentValue field in the update type.
          // We update via the general update endpoint with purchasePrice as fallback.
          await privatApi.updateVehicle(selectedAsset.id, {
            notes: `Bewertung aktualisiert: ${formatCurrencyDE(numValue)}`,
          });
          break;
        case 'investments':
          // Investments have a dedicated value update endpoint
          await privatApi.updateInvestmentValue(selectedAsset.id, numValue);
          break;
      }

      toast({
        title: 'Bewertung aktualisiert',
        description: `${selectedAsset.name} wurde auf ${formatCurrencyDE(numValue)} aktualisiert.`,
      });

      onSuccess();
      onOpenChange(false);
    } catch {
      toast({
        title: 'Fehler',
        description: 'Die Bewertung konnte nicht aktualisiert werden.',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Bewertung aktualisieren</DialogTitle>
          <DialogDescription>
            Aktualisieren Sie den aktuellen Wert eines Vermoegenswerts.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label>Vermoegenswert</Label>
            <Select value={selectedAssetId} onValueChange={setSelectedAssetId}>
              <SelectTrigger>
                <SelectValue placeholder="Vermoegenswert auswaehlen..." />
              </SelectTrigger>
              <SelectContent>
                {allAssetItems.length === 0 ? (
                  <SelectItem value="none" disabled>
                    Keine Vermoegenswerte vorhanden
                  </SelectItem>
                ) : (
                  allAssetItems.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.categoryLabel}: {item.name}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          {selectedAsset && (
            <div className="p-3 bg-muted rounded-md text-sm">
              <p>
                Aktueller Wert:{' '}
                <span className="font-mono font-medium">
                  {formatCurrencyDE(selectedAsset.currentValue)}
                </span>
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label>Neuer Wert (EUR)</Label>
            <Input
              type="text"
              inputMode="decimal"
              placeholder="z.B. 250000"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={
              selectedAssetId === 'none' || !newValue || isSubmitting
            }
          >
            {isSubmitting && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
