/**
 * InsuranceEditDialog - Dialog zum Bearbeiten einer Versicherung
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
import type { PrivatInsuranceUpdate, PrivatInsuranceWithDeadlines, InsuranceType } from '@/types/privat';

interface InsuranceEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  insurance: PrivatInsuranceWithDeadlines | null;
  onSubmit: (insuranceId: string, data: PrivatInsuranceUpdate) => Promise<void>;
  isLoading?: boolean;
}

const INSURANCE_TYPES: { value: InsuranceType; label: string }[] = [
  { value: 'health', label: 'Krankenversicherung' },
  { value: 'life', label: 'Lebensversicherung' },
  { value: 'liability', label: 'Haftpflicht' },
  { value: 'household', label: 'Hausrat' },
  { value: 'building', label: 'Gebäude' },
  { value: 'vehicle', label: 'KFZ' },
  { value: 'legal', label: 'Rechtsschutz' },
  { value: 'disability', label: 'Berufsunfähigkeit' },
  { value: 'travel', label: 'Reise' },
  { value: 'other', label: 'Sonstige' },
];

const PREMIUM_INTERVALS = [
  { value: 'monthly', label: 'Monatlich' },
  { value: 'quarterly', label: 'Vierteljährlich' },
  { value: 'semi_annual', label: 'Halbjährlich' },
  { value: 'annual', label: 'Jährlich' },
];

export function InsuranceEditDialog({
  open,
  onOpenChange,
  insurance,
  onSubmit,
  isLoading = false,
}: InsuranceEditDialogProps) {
  const [formData, setFormData] = React.useState<PrivatInsuranceUpdate>({});
  const [error, setError] = React.useState<string | null>(null);

  // Initialize form data when insurance changes
  React.useEffect(() => {
    if (insurance) {
      setFormData({
        name: insurance.name,
        insuranceType: insurance.insuranceType,
        provider: insurance.provider,
        policyNumber: insurance.policyNumber,
        premium: insurance.premium,
        premiumInterval: insurance.premiumInterval,
        coverageAmount: insurance.coverageAmount,
        deductible: insurance.deductible,
        endDate: insurance.endDate,
        cancellationPeriod: insurance.cancellationPeriod,
        autoRenewal: insurance.autoRenewal,
        notes: insurance.notes,
      });
    }
  }, [insurance]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!insurance) return;

    if (formData.name && !formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    try {
      await onSubmit(insurance.id, {
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

  if (!insurance) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Versicherung bearbeiten</DialogTitle>
            <DialogDescription>
              Ändern Sie die Details Ihrer Versicherung.
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
                placeholder="z.B. Private Haftpflicht"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Insurance Type */}
            <div className="grid gap-2">
              <Label htmlFor="insuranceType">Versicherungstyp</Label>
              <Select
                value={formData.insuranceType || ''}
                onValueChange={(value) => setFormData({ ...formData, insuranceType: value as InsuranceType })}
                disabled={isLoading}
              >
                <SelectTrigger id="insuranceType">
                  <SelectValue placeholder="Typ auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {INSURANCE_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Provider & Policy Number */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="provider">Versicherer</Label>
                <Input
                  id="provider"
                  value={formData.provider || ''}
                  onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
                  placeholder="z.B. Allianz"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="policyNumber">Policennummer</Label>
                <Input
                  id="policyNumber"
                  value={formData.policyNumber || ''}
                  onChange={(e) => setFormData({ ...formData, policyNumber: e.target.value })}
                  placeholder="z.B. VS-123456"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Premium & Interval */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="premium">Beitrag (€)</Label>
                <Input
                  id="premium"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.premium ?? ''}
                  onChange={(e) => setFormData({ ...formData, premium: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="premiumInterval">Zahlungsintervall</Label>
                <Select
                  value={formData.premiumInterval || ''}
                  onValueChange={(value) => setFormData({ ...formData, premiumInterval: value })}
                  disabled={isLoading}
                >
                  <SelectTrigger id="premiumInterval">
                    <SelectValue placeholder="Auswählen" />
                  </SelectTrigger>
                  <SelectContent>
                    {PREMIUM_INTERVALS.map((interval) => (
                      <SelectItem key={interval.value} value={interval.value}>
                        {interval.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Coverage & Deductible */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="coverageAmount">Versicherungssumme (€)</Label>
                <Input
                  id="coverageAmount"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.coverageAmount ?? ''}
                  onChange={(e) => setFormData({ ...formData, coverageAmount: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="deductible">Selbstbeteiligung (€)</Label>
                <Input
                  id="deductible"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.deductible ?? ''}
                  onChange={(e) => setFormData({ ...formData, deductible: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* End Date & Cancellation Period */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="endDate">Vertragsende</Label>
                <Input
                  id="endDate"
                  type="date"
                  value={formData.endDate || ''}
                  onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="cancellationPeriod">Kündigungsfrist (Monate)</Label>
                <Input
                  id="cancellationPeriod"
                  type="number"
                  min={0}
                  value={formData.cancellationPeriod ?? ''}
                  onChange={(e) => setFormData({ ...formData, cancellationPeriod: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="z.B. 3"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Auto Renewal */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="autoRenewal">Automatische Verlängerung</Label>
                <p className="text-sm text-muted-foreground">
                  Vertrag verlängert sich automatisch
                </p>
              </div>
              <Switch
                id="autoRenewal"
                checked={formData.autoRenewal}
                onCheckedChange={(checked) => setFormData({ ...formData, autoRenewal: checked })}
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

export default InsuranceEditDialog;
