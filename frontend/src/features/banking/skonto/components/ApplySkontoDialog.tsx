/**
 * ApplySkontoDialog - Dialog zum Anwenden von Skonto
 *
 * Bestätigungsdialog für Skonto-Anwendung bei Zahlung.
 *
 * Features:
 * - Eingabe des gezahlten Betrags
 * - Optional: Zahlungsdatum
 * - Force-Apply Option für abgelaufene Fristen
 * - Berechnung und Anzeige der Ersparnis
 */

import { useState, useMemo } from 'react';
import { Calendar, TrendingDown, AlertTriangle, CheckCircle } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useApplySkonto } from '../hooks';
import type { SkontoInfo } from '../types';

interface ApplySkontoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invoiceId: string;
  skontoInfo: SkontoInfo;
  onSuccess?: () => void;
}

export function ApplySkontoDialog({
  open,
  onOpenChange,
  invoiceId,
  skontoInfo,
  onSuccess,
}: ApplySkontoDialogProps) {
  const applySkontoMutation = useApplySkonto();

  // State
  const [paymentAmount, setPaymentAmount] = useState<string>(
    skontoInfo.amountWithSkonto?.toFixed(2) || ''
  );
  const [paymentDate, setPaymentDate] = useState<string>('');
  const [forceApply, setForceApply] = useState(false);

  // Formatiere Beträge
  const formattedSkontoAmount = useMemo(() => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(skontoInfo.amount || 0);
  }, [skontoInfo.amount]);

  const formattedExpectedAmount = useMemo(() => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(skontoInfo.amountWithSkonto || 0);
  }, [skontoInfo.amountWithSkonto]);

  // Berechne Differenz zum erwarteten Betrag
  const paymentDifference = useMemo(() => {
    const entered = parseFloat(paymentAmount.replace(',', '.'));
    if (isNaN(entered) || !skontoInfo.amountWithSkonto) return null;
    return entered - skontoInfo.amountWithSkonto;
  }, [paymentAmount, skontoInfo.amountWithSkonto]);

  // Validierung
  const isValid = useMemo(() => {
    const amount = parseFloat(paymentAmount.replace(',', '.'));
    if (isNaN(amount) || amount <= 0) return false;

    // Bei abgelaufener Frist muss Force-Apply aktiviert sein
    if (skontoInfo.isExpired && !forceApply) return false;

    return true;
  }, [paymentAmount, skontoInfo.isExpired, forceApply]);

  // Submit Handler
  const handleSubmit = async () => {
    if (!isValid) return;

    const amount = parseFloat(paymentAmount.replace(',', '.'));

    try {
      await applySkontoMutation.mutateAsync({
        invoiceId,
        data: {
          paymentAmount: amount,
          paymentDate: paymentDate || undefined,
          forceApply: forceApply || undefined,
        },
      });

      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      // Error wird durch useMutation Toast behandelt
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Skonto anwenden</DialogTitle>
          <DialogDescription>
            Skonto von {skontoInfo.percentage}% ({formattedSkontoAmount}) bei Zahlung anwenden
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Skonto-Info Alert */}
          <Alert>
            <TrendingDown className="h-4 w-4" />
            <AlertDescription>
              <strong>Erwarteter Betrag mit Skonto:</strong> {formattedExpectedAmount}
              <br />
              <span className="text-sm text-muted-foreground">
                Ersparnis: {formattedSkontoAmount}
              </span>
            </AlertDescription>
          </Alert>

          {/* Abgelaufene Frist Warnung */}
          {skontoInfo.isExpired && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                Die Skonto-Frist ist abgelaufen. Sie können Skonto trotzdem anwenden (z.B.
                Kulanzregelung), indem Sie unten die Option aktivieren.
              </AlertDescription>
            </Alert>
          )}

          {/* Gezahlter Betrag */}
          <div className="space-y-2">
            <Label htmlFor="payment-amount">
              Gezahlter Betrag <span className="text-destructive">*</span>
            </Label>
            <Input
              id="payment-amount"
              type="text"
              placeholder="0,00"
              value={paymentAmount}
              onChange={(e) => setPaymentAmount(e.target.value)}
              className="font-mono"
            />
            {paymentDifference !== null && Math.abs(paymentDifference) > 0.05 && (
              <p className="text-sm text-yellow-600 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                Differenz zum erwarteten Betrag:{' '}
                {new Intl.NumberFormat('de-DE', {
                  style: 'currency',
                  currency: 'EUR',
                  signDisplay: 'always',
                }).format(paymentDifference)}
              </p>
            )}
          </div>

          {/* Zahlungsdatum (optional) */}
          <div className="space-y-2">
            <Label htmlFor="payment-date">
              Zahlungsdatum <span className="text-muted-foreground">(optional)</span>
            </Label>
            <div className="relative">
              <Calendar className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                id="payment-date"
                type="date"
                value={paymentDate}
                onChange={(e) => setPaymentDate(e.target.value)}
                className="pl-9"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Leer lassen für aktuelles Datum
            </p>
          </div>

          {/* Force Apply bei abgelaufener Frist */}
          {skontoInfo.isExpired && (
            <div className="flex items-center space-x-2 pt-2 border-t">
              <Checkbox
                id="force-apply"
                checked={forceApply}
                onCheckedChange={(checked) => setForceApply(checked === true)}
              />
              <Label
                htmlFor="force-apply"
                className="text-sm font-normal cursor-pointer"
              >
                Skonto trotz abgelaufener Frist anwenden (manuell freigegeben)
              </Label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || applySkontoMutation.isPending}
          >
            {applySkontoMutation.isPending ? (
              <>Wird angewendet...</>
            ) : (
              <>
                <CheckCircle className="w-4 h-4 mr-2" />
                Skonto anwenden
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
