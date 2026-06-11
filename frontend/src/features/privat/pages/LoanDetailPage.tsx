/**
 * LoanDetailPage - Kredit-Detailansicht
 *
 * Zeigt alle Details eines Kredits inkl. Zahlungsübersicht
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { ArrowLeft, Edit, Trash2, Landmark, Euro, Calendar, TrendingDown, Loader2, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import * as privatApi from '../api/privat-api';
import type { PrivatLoanWithStats, PrivatLoanUpdate } from '@/types/privat';
import { LoanEditDialog } from '../components/finances/LoanEditDialog';

const LOAN_TYPE_LABELS: Record<string, string> = {
  mortgage: 'Hypothek/Baufinanzierung',
  personal: 'Privatkredit',
  car: 'Autokredit',
  student: 'Studienkredit',
  business: 'Geschäftskredit',
  other: 'Sonstiges',
};

export function LoanDetailPage() {
  const navigate = useNavigate();
  const { loanId } = useParams({ strict: false }) as { loanId: string };

  const [loan, setLoan] = React.useState<PrivatLoanWithStats | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false);
  const [showEditDialog, setShowEditDialog] = React.useState(false);
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Load loan details
  React.useEffect(() => {
    const loadLoan = async () => {
      if (!loanId) {
        setError(new Error('Keine Kredit-ID angegeben'));
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const data = await privatApi.getLoan(loanId);
        setLoan(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden des Kredits'));
      } finally {
        setIsLoading(false);
      }
    };
    loadLoan();
  }, [loanId]);

  const handleEdit = async (lId: string, data: PrivatLoanUpdate) => {
    setIsUpdating(true);
    try {
      const updated = await privatApi.updateLoan(lId, data);
      setLoan(updated);
      toast.success('Kredit aktualisiert');
    } catch (err) {
      toast.error('Fehler beim Aktualisieren');
      throw err;
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!loan) return;

    try {
      await privatApi.deleteLoan(loan.id);
      toast.success('Kredit gelöscht');
      navigate({ to: '/privat/finanzen' });
    } catch (err) {
      toast.error('Fehler beim Löschen des Kredits');
    } finally {
      setShowDeleteDialog(false);
    }
  };

  const handleBack = () => {
    navigate({ to: '/privat/finanzen' });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !loan) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <p className="text-destructive mb-4">{error?.message || 'Kredit nicht gefunden'}</p>
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    );
  }

  // Calculate progress
  const paidPercentage = loan.principalAmount > 0
    ? ((loan.principalAmount - loan.currentBalance) / loan.principalAmount) * 100
    : 0;

  // Check if payment is due soon
  const paymentDue = loan.nextPaymentDate ? new Date(loan.nextPaymentDate) : null;
  const daysUntilPayment = paymentDue ? Math.ceil((paymentDue.getTime() - Date.now()) / (1000 * 60 * 60 * 24)) : null;
  const isPaymentSoon = daysUntilPayment !== null && daysUntilPayment <= 7 && daysUntilPayment >= 0;
  const isPaymentOverdue = daysUntilPayment !== null && daysUntilPayment < 0;

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{loan.name}</h1>
            <p className="text-muted-foreground">
              {LOAN_TYPE_LABELS[loan.loanType] || loan.loanType}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowEditDialog(true)}>
            <Edit className="mr-2 h-4 w-4" />
            Bearbeiten
          </Button>
          <Button variant="destructive" onClick={() => setShowDeleteDialog(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            Löschen
          </Button>
        </div>
      </div>

      {/* Payment Alert */}
      {(isPaymentSoon || isPaymentOverdue) && (
        <Card className={isPaymentOverdue ? 'border-destructive' : 'border-yellow-500'}>
          <CardContent className="flex items-center gap-3 py-4">
            <AlertTriangle className={`h-5 w-5 ${isPaymentOverdue ? 'text-destructive' : 'text-yellow-500'}`} />
            <div>
              <p className="font-medium">
                {isPaymentOverdue
                  ? `Zahlung überfällig (${Math.abs(daysUntilPayment!)} Tage)`
                  : `Nächste Rate in ${daysUntilPayment} Tagen`
                }
              </p>
              {paymentDue && (
                <p className="text-sm text-muted-foreground">
                  Fällig am {paymentDue.toLocaleDateString('de-DE')}
                  {loan.monthlyPayment && ` - ${loan.monthlyPayment.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}`}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Progress Card */}
      <Card>
        <CardHeader>
          <CardTitle>Tilgungsfortschritt</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between text-sm mb-2">
            <span>Getilgt</span>
            <span>{paidPercentage.toFixed(1)}%</span>
          </div>
          <Progress value={paidPercentage} className="h-3" />
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>
              {(loan.principalAmount - loan.currentBalance).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })} von {loan.principalAmount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
            </span>
            <span>Restschuld: {loan.currentBalance.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
          </div>
        </CardContent>
      </Card>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Basic Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Landmark className="h-5 w-5" />
              Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {loan.lender && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kreditgeber</span>
                <span>{loan.lender}</span>
              </div>
            )}
            {loan.accountNumber && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kontonummer</span>
                <span className="font-mono">{loan.accountNumber}</span>
              </div>
            )}
            {loan.interestRate !== undefined && loan.interestRate !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Zinssatz</span>
                <span>{loan.interestRate.toFixed(2)}%</span>
              </div>
            )}
            {loan.startDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Beginn</span>
                <span>{new Date(loan.startDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
            {loan.endDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Laufzeitende</span>
                <span>{new Date(loan.endDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Payment Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Euro className="h-5 w-5" />
              Zahlungen
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {loan.monthlyPayment !== undefined && loan.monthlyPayment !== null && (
              <div className="text-center py-4">
                <p className="text-3xl font-bold">
                  {loan.monthlyPayment.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                </p>
                <p className="text-sm text-muted-foreground">Monatliche Rate</p>
              </div>
            )}
            {loan.nextPaymentDate && (
              <>
                <Separator />
                <div className="flex items-center gap-2 text-sm">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Nächste Rate:</span>
                  <span>{new Date(loan.nextPaymentDate).toLocaleDateString('de-DE')}</span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Statistics Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingDown className="h-5 w-5" />
              Statistik
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Bereits bezahlt</span>
              <span className="text-green-600">{loan.totalPaid.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Davon Zinsen</span>
              <span>{loan.totalInterestPaid.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
            </div>
            {loan.remainingMonths !== undefined && loan.remainingMonths !== null && (
              <>
                <Separator />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Restlaufzeit</span>
                  <span>{loan.remainingMonths} Monate</span>
                </div>
              </>
            )}
            {loan.payoffDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Voraussichtlich abbezahlt</span>
                <span>{new Date(loan.payoffDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Notes Section */}
      {loan.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notizen</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{loan.notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Edit Dialog */}
      <LoanEditDialog
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        loan={loan}
        onSubmit={handleEdit}
        isLoading={isUpdating}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Kredit löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie den Kredit "{loan.name}" wirklich löschen?
              Alle zugehörigen Zahlungen und Dokumente werden ebenfalls gelöscht.
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
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

export default LoanDetailPage;
