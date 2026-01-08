/**
 * InvestmentCreateDialog - Dialog zum Erstellen einer neuen Geldanlage
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
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import type { PrivatInvestmentCreate, InvestmentType } from '@/types/privat';

interface InvestmentCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: PrivatInvestmentCreate) => Promise<void>;
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

export function InvestmentCreateDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: InvestmentCreateDialogProps) {
  const [formData, setFormData] = React.useState<PrivatInvestmentCreate>({
    name: '',
    investmentType: 'savings',
    initialAmount: 0,
    currentValue: 0,
    isTaxable: true,
  });
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    if (formData.initialAmount < 0) {
      setError('Anlagesumme kann nicht negativ sein');
      return;
    }

    if (formData.currentValue < 0) {
      setError('Aktueller Wert kann nicht negativ sein');
      return;
    }

    try {
      await onSubmit({
        ...formData,
        name: formData.name.trim(),
        interestRate: formData.interestRate || undefined,
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
      investmentType: 'savings',
      initialAmount: 0,
      currentValue: 0,
      isTaxable: true,
    });
    setError(null);
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      resetForm();
    }
    onOpenChange(newOpen);
  };

  // Auto-fill current value when initial amount changes (for new investments)
  const handleInitialAmountChange = (value: number) => {
    setFormData({
      ...formData,
      initialAmount: value,
      currentValue: formData.currentValue === formData.initialAmount ? value : formData.currentValue,
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Neue Geldanlage</DialogTitle>
            <DialogDescription>
              Erfassen Sie eine neue Geldanlage in Ihrem Portfolio.
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
                placeholder="z.B. Tagesgeldkonto ING"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Investment Type */}
            <div className="grid gap-2">
              <Label htmlFor="investmentType">Anlageart</Label>
              <Select
                value={formData.investmentType}
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

            {/* Institution & Account */}
            <div className="grid grid-cols-2 gap-4">
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
              <div className="grid gap-2">
                <Label htmlFor="accountNumber">Kontonummer/Depot</Label>
                <Input
                  id="accountNumber"
                  value={formData.accountNumber || ''}
                  onChange={(e) => setFormData({ ...formData, accountNumber: e.target.value })}
                  placeholder="z.B. DE89..."
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Initial Amount & Current Value */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="initialAmount">
                  Anlagesumme (€) <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="initialAmount"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.initialAmount || ''}
                  onChange={(e) => handleInitialAmountChange(Number(e.target.value) || 0)}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="currentValue">
                  Aktueller Wert (€) <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="currentValue"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.currentValue || ''}
                  onChange={(e) => setFormData({ ...formData, currentValue: Number(e.target.value) || 0 })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Interest Rate */}
            <div className="grid gap-2">
              <Label htmlFor="interestRate">Zinssatz/Rendite (%)</Label>
              <Input
                id="interestRate"
                type="number"
                min={-100}
                max={1000}
                step={0.01}
                value={formData.interestRate || ''}
                onChange={(e) => setFormData({ ...formData, interestRate: e.target.value ? Number(e.target.value) : undefined })}
                placeholder="z.B. 2.5"
                disabled={isLoading}
              />
            </div>

            {/* Dates */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="startDate">Startdatum</Label>
                <Input
                  id="startDate"
                  type="date"
                  value={formData.startDate || ''}
                  onChange={(e) => setFormData({ ...formData, startDate: e.target.value })}
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

            {/* Taxable */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="isTaxable">Steuerpflichtig</Label>
                <p className="text-sm text-muted-foreground">
                  Erträge unterliegen der Kapitalertragsteuer
                </p>
              </div>
              <Switch
                id="isTaxable"
                checked={formData.isTaxable}
                onCheckedChange={(checked) => setFormData({ ...formData, isTaxable: checked })}
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

export default InvestmentCreateDialog;
