/**
 * InvestmentEditDialog - Dialog zum Bearbeiten einer Geldanlage
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
import type { PrivatInvestmentUpdate, PrivatInvestmentWithStats, InvestmentType } from '@/types/privat';

interface InvestmentEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  investment: PrivatInvestmentWithStats | null;
  onSubmit: (investmentId: string, data: PrivatInvestmentUpdate) => Promise<void>;
  isLoading?: boolean;
}

const INVESTMENT_TYPES: { value: InvestmentType; label: string }[] = [
  { value: 'savings', label: 'Sparkonto/Tagesgeld' },
  { value: 'stocks', label: 'Aktien' },
  { value: 'bonds', label: 'Anleihen' },
  { value: 'fund', label: 'Fonds' },
  { value: 'etf', label: 'ETF' },
  { value: 'real_estate', label: 'Immobilienfonds' },
  { value: 'crypto', label: 'Kryptowährungen' },
  { value: 'pension', label: 'Altersvorsorge' },
  { value: 'other', label: 'Sonstiges' },
];

export function InvestmentEditDialog({
  open,
  onOpenChange,
  investment,
  onSubmit,
  isLoading = false,
}: InvestmentEditDialogProps) {
  const [formData, setFormData] = React.useState<PrivatInvestmentUpdate>({});
  const [error, setError] = React.useState<string | null>(null);

  // Initialize form data when investment changes
  React.useEffect(() => {
    if (investment) {
      setFormData({
        name: investment.name,
        investmentType: investment.investmentType,
        institution: investment.institution,
        currentValue: investment.currentValue,
        interestRate: investment.interestRate,
        maturityDate: investment.maturityDate,
        notes: investment.notes,
      });
    }
  }, [investment]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!investment) return;

    if (formData.name && !formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    if (formData.currentValue !== undefined && formData.currentValue < 0) {
      setError('Aktueller Wert kann nicht negativ sein');
      return;
    }

    try {
      await onSubmit(investment.id, {
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

  if (!investment) return null;

  // Calculate return percentage for display
  const returnPercentage = investment.initialAmount > 0
    ? ((investment.currentValue - investment.initialAmount) / investment.initialAmount * 100).toFixed(2)
    : '0.00';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Geldanlage bearbeiten</DialogTitle>
            <DialogDescription>
              Ändern Sie die Details Ihrer Geldanlage.
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
                placeholder="z.B. Tagesgeldkonto ING"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Investment Type */}
            <div className="grid gap-2">
              <Label htmlFor="investmentType">Anlageart</Label>
              <Select
                value={formData.investmentType || ''}
                onValueChange={(value) => setFormData({ ...formData, investmentType: value as InvestmentType })}
                disabled={isLoading}
              >
                <SelectTrigger id="investmentType">
                  <SelectValue placeholder="Art auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {INVESTMENT_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Institution */}
            <div className="grid gap-2">
              <Label htmlFor="institution">Institut/Bank</Label>
              <Input
                id="institution"
                value={formData.institution || ''}
                onChange={(e) => setFormData({ ...formData, institution: e.target.value })}
                placeholder="z.B. ING"
                disabled={isLoading}
              />
            </div>

            {/* Current Value */}
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
              <p className="text-xs text-muted-foreground">
                Anlagesumme: {investment.initialAmount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })} |
                Rendite: {returnPercentage}%
              </p>
            </div>

            {/* Interest Rate & Maturity */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="interestRate">Zinssatz/Rendite (%)</Label>
                <Input
                  id="interestRate"
                  type="number"
                  min={-100}
                  max={1000}
                  step={0.01}
                  value={formData.interestRate ?? ''}
                  onChange={(e) => setFormData({ ...formData, interestRate: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="z.B. 2.5"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="maturityDate">Fälligkeitsdatum</Label>
                <Input
                  id="maturityDate"
                  type="date"
                  value={formData.maturityDate || ''}
                  onChange={(e) => setFormData({ ...formData, maturityDate: e.target.value })}
                  disabled={isLoading}
                />
              </div>
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

export default InvestmentEditDialog;
