/**
 * LoanEditDialog - Dialog zum Bearbeiten eines Kredits
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
import type { PrivatLoanUpdate, PrivatLoanWithStats, LoanType } from '@/types/privat';

interface LoanEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  loan: PrivatLoanWithStats | null;
  onSubmit: (loanId: string, data: PrivatLoanUpdate) => Promise<void>;
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

export function LoanEditDialog({
  open,
  onOpenChange,
  loan,
  onSubmit,
  isLoading = false,
}: LoanEditDialogProps) {
  const [formData, setFormData] = React.useState<PrivatLoanUpdate>({});
  const [error, setError] = React.useState<string | null>(null);

  // Initialize form data when loan changes
  React.useEffect(() => {
    if (loan) {
      setFormData({
        name: loan.name,
        loanType: loan.loanType,
        lender: loan.lender,
        interestRate: loan.interestRate,
        monthlyPayment: loan.monthlyPayment,
        nextPaymentDate: loan.nextPaymentDate,
        notes: loan.notes,
      });
    }
  }, [loan]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!loan) return;

    if (formData.name && !formData.name.trim()) {
      setError('Name ist erforderlich');
      return;
    }

    try {
      await onSubmit(loan.id, {
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

  if (!loan) return null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[525px] max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Kredit bearbeiten</DialogTitle>
            <DialogDescription>
              Ändern Sie die Details Ihres Kredits.
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
                placeholder="z.B. Baufinanzierung Haus"
                maxLength={100}
                disabled={isLoading}
              />
            </div>

            {/* Loan Type */}
            <div className="grid gap-2">
              <Label htmlFor="loanType">Kreditart</Label>
              <Select
                value={formData.loanType || ''}
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

            {/* Lender */}
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
                  value={formData.interestRate ?? ''}
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
                  value={formData.monthlyPayment ?? ''}
                  onChange={(e) => setFormData({ ...formData, monthlyPayment: e.target.value ? Number(e.target.value) : undefined })}
                  placeholder="0.00"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Next Payment Date */}
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

            {/* Info Box */}
            <div className="p-3 bg-muted rounded-lg text-sm">
              <p className="font-medium mb-1">Hinweis:</p>
              <p className="text-muted-foreground">
                Um die Restschuld zu aktualisieren, erfassen Sie bitte eine Zahlung.
                Die Darlehenssumme kann nach Erstellung nicht mehr geändert werden.
              </p>
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

export default LoanEditDialog;
