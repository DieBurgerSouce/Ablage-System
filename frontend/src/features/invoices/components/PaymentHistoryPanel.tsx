/**
 * PaymentHistoryPanel - Teilzahlungs-Verwaltungskomponente
 *
 * Zeigt Zahlungsverlauf einer Rechnung und ermöglicht:
 * - Neue Teilzahlung erfassen
 * - Zahlungshistorie anzeigen
 * - Einzelne Zahlungen löschen
 * - Ausstehenden Betrag anzeigen
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Banknote,
  Plus,
  Trash2,
  Loader2,
  CheckCircle,
  Clock,
  AlertCircle,
  CreditCard,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { UI_LABELS, type InvoiceTrackingResponse, type PaymentTransaction } from '../types/invoice-types';
import { formatCurrency, formatDate, formatDateTime } from '@/features/banking/utils/format';
import { usePayments, useAddPayment, useDeletePayment } from '../hooks/use-invoice-queries';
import { useToast } from '@/hooks/use-toast';

interface PaymentHistoryPanelProps {
  invoice: InvoiceTrackingResponse;
  className?: string;
}

const PAYMENT_METHODS = [
  { value: 'bank_transfer', label: 'Banküberweisung' },
  { value: 'cash', label: 'Barzahlung' },
  { value: 'card', label: 'Kartenzahlung' },
  { value: 'paypal', label: 'PayPal' },
  { value: 'sepa', label: 'SEPA-Lastschrift' },
  { value: 'other', label: 'Sonstige' },
];

const RECONCILIATION_STATUS_CONFIG = {
  pending: {
    label: UI_LABELS.partialPaymentPending,
    icon: Clock,
    className: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  },
  matched: {
    label: UI_LABELS.partialPaymentReconciled,
    icon: CheckCircle,
    className: 'bg-green-50 text-green-700 border-green-200',
  },
  unmatched: {
    label: UI_LABELS.partialPaymentUnmatched,
    icon: AlertCircle,
    className: 'bg-red-50 text-red-700 border-red-200',
  },
};

export function PaymentHistoryPanel({ invoice, className }: PaymentHistoryPanelProps) {
  const { toast } = useToast();
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [newPaymentAmount, setNewPaymentAmount] = useState<string>('');
  const [newPaymentMethod, setNewPaymentMethod] = useState<string>('bank_transfer');
  const [newPaymentReference, setNewPaymentReference] = useState<string>('');
  const [newPaymentNotes, setNewPaymentNotes] = useState<string>('');
  const [deletingPaymentId, setDeletingPaymentId] = useState<string | null>(null);

  const paymentsQuery = usePayments(invoice.id);
  const addPayment = useAddPayment();
  const deletePayment = useDeletePayment();

  const payments = paymentsQuery.data?.payments ?? [];
  const totalPaid = paymentsQuery.data?.totalPaid ?? 0;
  const outstandingAmount = paymentsQuery.data?.outstandingAmount ?? invoice.amount;
  const isFullyPaid = paymentsQuery.data?.isFullyPaid ?? false;

  // Handler
  const handleAddPayment = async () => {
    const amount = parseFloat(newPaymentAmount);
    if (isNaN(amount) || amount <= 0) {
      toast({
        title: 'Fehler',
        description: 'Bitte einen gültigen Betrag eingeben',
        variant: 'destructive',
      });
      return;
    }

    if (amount > outstandingAmount) {
      toast({
        title: 'Warnung',
        description: `Der Betrag übersteigt den ausstehenden Betrag von ${formatCurrency(outstandingAmount)}`,
        variant: 'destructive',
      });
      return;
    }

    try {
      await addPayment.mutateAsync({
        invoiceId: invoice.id,
        data: {
          amount,
          paymentMethod: newPaymentMethod,
          reference: newPaymentReference || undefined,
          notes: newPaymentNotes || undefined,
        },
      });
      toast({
        title: 'Erfolg',
        description: UI_LABELS.successAddPayment,
      });
      setIsAddDialogOpen(false);
      // Reset form
      setNewPaymentAmount('');
      setNewPaymentMethod('bank_transfer');
      setNewPaymentReference('');
      setNewPaymentNotes('');
    } catch {
      toast({
        title: 'Fehler',
        description: UI_LABELS.errorAddPayment,
        variant: 'destructive',
      });
    }
  };

  const handleDeletePayment = async (paymentId: string) => {
    setDeletingPaymentId(paymentId);
    try {
      await deletePayment.mutateAsync({
        invoiceId: invoice.id,
        paymentId,
      });
      toast({
        title: 'Erfolg',
        description: UI_LABELS.successDeletePayment,
      });
    } catch {
      toast({
        title: 'Fehler',
        description: UI_LABELS.errorDeletePayment,
        variant: 'destructive',
      });
    } finally {
      setDeletingPaymentId(null);
    }
  };

  const handleSetOutstandingAmount = () => {
    setNewPaymentAmount(outstandingAmount.toFixed(2));
  };

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Banknote className="w-4 h-4" />
              {UI_LABELS.partialPaymentTitle}
            </CardTitle>
            <CardDescription>
              {payments.length === 0
                ? 'Noch keine Zahlungen erfasst'
                : `${payments.length} ${payments.length === 1 ? 'Zahlung' : 'Zahlungen'} erfasst`}
            </CardDescription>
          </div>
          {!isFullyPaid && (
            <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="w-4 h-4 mr-1" />
                  {UI_LABELS.partialPaymentAdd}
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{UI_LABELS.partialPaymentAdd}</DialogTitle>
                  <DialogDescription>
                    Neue Zahlung für diese Rechnung erfassen.
                    Ausstehend: {formatCurrency(outstandingAmount)}
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <Label htmlFor="payment-amount">{UI_LABELS.partialPaymentAmount}</Label>
                    <div className="flex items-center gap-2">
                      <Input
                        id="payment-amount"
                        type="number"
                        step="0.01"
                        min="0.01"
                        max={outstandingAmount}
                        value={newPaymentAmount}
                        onChange={(e) => setNewPaymentAmount(e.target.value)}
                        placeholder="z.B. 500.00"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleSetOutstandingAmount}
                      >
                        Alles
                      </Button>
                    </div>
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="payment-method">{UI_LABELS.partialPaymentMethod}</Label>
                    <Select
                      value={newPaymentMethod}
                      onValueChange={setNewPaymentMethod}
                    >
                      <SelectTrigger id="payment-method">
                        <SelectValue placeholder="Zahlungsart wählen" />
                      </SelectTrigger>
                      <SelectContent>
                        {PAYMENT_METHODS.map((method) => (
                          <SelectItem key={method.value} value={method.value}>
                            {method.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="payment-reference">{UI_LABELS.partialPaymentReference}</Label>
                    <Input
                      id="payment-reference"
                      value={newPaymentReference}
                      onChange={(e) => setNewPaymentReference(e.target.value)}
                      placeholder="z.B. Verwendungszweck, Transaktionsnr."
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="payment-notes">Notizen</Label>
                    <Input
                      id="payment-notes"
                      value={newPaymentNotes}
                      onChange={(e) => setNewPaymentNotes(e.target.value)}
                      placeholder="Optionale Notizen"
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setIsAddDialogOpen(false)}
                  >
                    Abbrechen
                  </Button>
                  <Button
                    onClick={handleAddPayment}
                    disabled={addPayment.isPending}
                  >
                    {addPayment.isPending && (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    )}
                    Zahlung erfassen
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Zusammenfassung */}
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-muted-foreground">Rechnungsbetrag</div>
            <div className="font-medium">{formatCurrency(invoice.amount)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">{UI_LABELS.partialPaymentTotal}</div>
            <div className="font-medium text-green-600">{formatCurrency(totalPaid)}</div>
          </div>
          <div>
            <div className="text-muted-foreground">{UI_LABELS.partialPaymentOutstanding}</div>
            <div className={cn('font-medium', isFullyPaid ? 'text-green-600' : 'text-orange-600')}>
              {formatCurrency(outstandingAmount)}
            </div>
          </div>
        </div>

        {/* Fortschrittsbalken */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Zahlungsfortschritt</span>
            <span>{Math.round((totalPaid / invoice.amount) * 100)}%</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full transition-all',
                isFullyPaid ? 'bg-green-500' : 'bg-blue-500'
              )}
              style={{ width: `${Math.min((totalPaid / invoice.amount) * 100, 100)}%` }}
            />
          </div>
        </div>

        {isFullyPaid && (
          <div className="flex items-center gap-2 p-3 bg-green-50 text-green-700 rounded-md">
            <CheckCircle className="w-5 h-5" />
            <div className="font-medium">Vollständig bezahlt</div>
          </div>
        )}

        {/* Zahlungsliste */}
        {payments.length > 0 && (
          <>
            <Separator />
            <div className="space-y-3">
              <div className="text-sm font-medium">{UI_LABELS.partialPaymentHistory}</div>
              {paymentsQuery.isLoading ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="space-y-2">
                  {payments.map((payment) => (
                    <PaymentItem
                      key={payment.id}
                      payment={payment}
                      onDelete={() => handleDeletePayment(payment.id)}
                      isDeleting={deletingPaymentId === payment.id}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* Keine Zahlungen */}
        {payments.length === 0 && !paymentsQuery.isLoading && (
          <div className="text-center py-6 text-muted-foreground">
            <CreditCard className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>Noch keine Zahlungen erfasst</p>
            <p className="text-xs mt-1">
              Klicken Sie auf &quot;{UI_LABELS.partialPaymentAdd}&quot;, um eine Zahlung hinzuzufuegen.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Unterkomponente für einzelne Zahlung
function PaymentItem({
  payment,
  onDelete,
  isDeleting,
}: {
  payment: PaymentTransaction;
  onDelete: () => void;
  isDeleting: boolean;
}) {
  const statusConfig = RECONCILIATION_STATUS_CONFIG[payment.reconciliationStatus];
  const StatusIcon = statusConfig.icon;
  const paymentMethod = PAYMENT_METHODS.find((m) => m.value === payment.paymentMethod);

  return (
    <div className="flex items-center justify-between p-3 bg-muted/50 rounded-md">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
          <Banknote className="w-5 h-5 text-green-600" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-green-600">
              +{formatCurrency(payment.amount)}
            </span>
            <Badge
              variant="outline"
              className={cn('text-xs', statusConfig.className)}
            >
              <StatusIcon className="w-3 h-3 mr-1" />
              {statusConfig.label}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground">
            {formatDateTime(payment.paidAt)}
            {paymentMethod && ` • ${paymentMethod.label}`}
            {payment.reference && ` • ${payment.reference}`}
          </div>
        </div>
      </div>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="text-muted-foreground hover:text-destructive"
            disabled={isDeleting}
          >
            {isDeleting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Zahlung löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Zahlung über {formatCurrency(payment.amount)} vom{' '}
              {formatDate(payment.paidAt)} wirklich löschen? Diese Aktion kann nicht
              rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={onDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
