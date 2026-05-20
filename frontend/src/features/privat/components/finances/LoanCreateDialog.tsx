/**
 * LoanCreateDialog - Dialog zum Erstellen eines neuen Kredits
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
import type { PrivatLoanCreate, LoanType } from '@/types/privat';

interface LoanCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (data: PrivatLoanCreate) => Promise<void>;
  isLoading?: boolean;
}

const LOAN_TYPES: { value: LoanType; label: string }[] = [
  { value: 'mortgage', label: 'Hypothek/Baufinanzierung' },
  { value: 'personal', label: 'Privatkredit' },
  { value: 'car', label: 'Autokredit' },
  { value: 'student', label: 'Studienkredit' },
  { value: 'business', label: 'Geschäftskredit' },
  { value: 'other', label: 'Sonstiges' },
];

export function LoanCreateDialog({
  open,
  onOpenChange,
  onSubmit,
  isLoading = false,
}: LoanCreateDialogProps) {
  const [formData, setFormData] = React.useState<PrivatLoanCreate>({
    name: '',
    loanType: 'personal',
    principalAmount: 0,
    currentBalance: 0,
  });
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    if (formData.principalAmount <= 0) {
      setError('Darlehenssumme muss größer als 0 sein');
      return;
    }

    if (formData.currentBalance < 0) {
      setError('Restschuld kann nicht negativ sein');
      return;
    }

    try {
      await onSubmit({
        ...formData,
        name: formData.name.trim(),
        interestRate: formData.interestRate || undefined,
        monthlyPayment: formData.monthlyPayment || undefined,
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
      loanType: 'personal',
      principalAmount: 0,
      currentBalance: 0,
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
            <DialogTitle>Neuer Kredit</DialogTitle>
            <DialogDescription>
              Erfassen Sie einen neuen Kredit in Ihrem Portfolio.
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
                placeholder="z.B. Baufinanzierung Haus"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Loan Type */}
            <div className="grid gap-2">
              <Label htmlFor="loanType">Kreditart</Label>
              <Select
                value={formData.loanType}
                onValueChange={(value) => setFormData({ ...formData, loanType: value as LoanType })}
                disabled={isLoading}
              >
                <SelectTrigger id="loanType">
                  <SelectValue placeholder="Art auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {LOAN_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Lender & Account */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="lender">Kreditgeber</Label>
                <Input
                  id="lender"
                  value={formData.lender || ''}
                  onChange={(e) => setFormData({ ...formData, lender: e.target.value })}
                  placeholder="z.B. Sparkasse"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="accountNumber">Kontonummer</Label>
                <Input
                  id="accountNumber"
                  value={formData.accountNumber || ''}
                  onChange={(e) => setFormData({ ...formData, accountNumber: e.target.value })}
                  placeholder="z.B. DE89..."
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Principal & Current Balance */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="principalAmount">
                  Darlehenssumme (€) <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="principalAmount"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.principalAmount || ''}
                  onChange={(e) => setFormData({ ...formData, principalAmount: Number(e.target.value) || 0 })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="currentBalance">
                  Aktuelle Restschuld (€) <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="currentBalance"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.currentBalance || ''}
                  onChange={(e) => setFormData({ ...formData, currentBalance: Number(e.target.value) || 0 })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Interest Rate & Monthly Payment */}
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="interestRate">Zinssatz (%)</Label>
                <Input
                  id="interestRate"
                  type="number"
                  min={0}
                  max={100}
                  step={0.01}
                  value={formData.interestRate || ''}
                  onChange={(e) => setFormData({ ...formData, interestRate: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="z.B. 3.5"
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="monthlyPayment">Monatliche Rate (€)</Label>
                <Input
                  id="monthlyPayment"
                  type="number"
                  min={0}
                  step={0.01}
                  value={formData.monthlyPayment || ''}
                  onChange={(e) => setFormData({ ...formData, monthlyPayment: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Dates */}
            <div className="grid grid-cols-3 gap-4">
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
                <Label htmlFor="endDate">Enddatum</Label>
                <Input
                  id="endDate"
                  type="date"
                  value={formData.endDate || ''}
                  onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                  disabled={isLoading}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="nextPaymentDate">Nächste Rate</Label>
                <Input
                  id="nextPaymentDate"
                  type="date"
                  value={formData.nextPaymentDate || ''}
                  onChange={(e) => setFormData({ ...formData, nextPaymentDate: e.target.value })}
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
              Erstellen
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default LoanCreateDialog;
