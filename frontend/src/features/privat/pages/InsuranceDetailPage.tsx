/**
 * InsuranceDetailPage - Versicherungs-Detailansicht
 *
 * Zeigt alle Details einer Versicherung inkl. Zahlungen und Fristen
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { ArrowLeft, Edit, Trash2, Shield, Euro, Calendar, Clock, AlertTriangle, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
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
import type { PrivatInsuranceWithDeadlines, PrivatInsuranceUpdate } from '@/types/privat';
import { InsuranceEditDialog } from '../components/insurances/InsuranceEditDialog';
import { DocumentUploadSection } from '../components/shared/DocumentUploadSection';

const INSURANCE_TYPE_LABELS: Record<string, string> = {
  health: 'Krankenversicherung',
  life: 'Lebensversicherung',
  liability: 'Haftpflicht',
  household: 'Hausrat',
  building: 'Gebäude',
  vehicle: 'KFZ',
  legal: 'Rechtsschutz',
  disability: 'Berufsunfähigkeit',
  travel: 'Reise',
  other: 'Sonstige',
};

const PREMIUM_INTERVAL_LABELS: Record<string, string> = {
  monthly: 'Monatlich',
  quarterly: 'Vierteljährlich',
  semi_annual: 'Halbjährlich',
  annual: 'Jährlich',
};

export function InsuranceDetailPage() {
  const navigate = useNavigate();
  const { insuranceId } = useParams({ strict: false }) as { insuranceId: string };

  const [insurance, setInsurance] = React.useState<PrivatInsuranceWithDeadlines | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false);
  const [showEditDialog, setShowEditDialog] = React.useState(false);
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Load insurance details
  React.useEffect(() => {
    const loadInsurance = async () => {
      if (!insuranceId) {
        setError(new Error('Keine Versicherungs-ID angegeben'));
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const data = await privatApi.getInsurance(insuranceId);
        setInsurance(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden der Versicherung'));
      } finally {
        setIsLoading(false);
      }
    };
    loadInsurance();
  }, [insuranceId]);

  const handleEdit = async (insId: string, data: PrivatInsuranceUpdate) => {
    setIsUpdating(true);
    try {
      const updated = await privatApi.updateInsurance(insId, data);
      setInsurance(updated);
      toast.success('Versicherung aktualisiert');
    } catch (err) {
      toast.error('Fehler beim Aktualisieren');
      throw err;
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!insurance) return;

    try {
      await privatApi.deleteInsurance(insurance.id);
      toast.success('Versicherung gelöscht');
      navigate({ to: '/privat/versicherungen' });
    } catch (err) {
      toast.error('Fehler beim Löschen der Versicherung');
    } finally {
      setShowDeleteDialog(false);
    }
  };

  const handleBack = () => {
    navigate({ to: '/privat/versicherungen' });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !insurance) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <p className="text-destructive mb-4">{error?.message || 'Versicherung nicht gefunden'}</p>
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    );
  }

  const isPaymentSoon = insurance.daysUntilPayment !== undefined && insurance.daysUntilPayment <= 7;
  const isPaymentOverdue = insurance.daysUntilPayment !== undefined && insurance.daysUntilPayment < 0;

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{insurance.name}</h1>
            <p className="text-muted-foreground">
              {INSURANCE_TYPE_LABELS[insurance.insuranceType] || insurance.insuranceType}
            </p>
          </div>
          {insurance.autoRenewal && (
            <Badge variant="outline">Auto-Verlängerung</Badge>
          )}
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
                  ? `Zahlung überfällig (${Math.abs(insurance.daysUntilPayment!)} Tage)`
                  : `Nächste Zahlung in ${insurance.daysUntilPayment} Tagen`
                }
              </p>
              {insurance.upcomingPayment && (
                <p className="text-sm text-muted-foreground">
                  Fällig am {new Date(insurance.upcomingPayment).toLocaleDateString('de-DE')}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Basic Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {insurance.provider && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Versicherer</span>
                <span>{insurance.provider}</span>
              </div>
            )}
            {insurance.policyNumber && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Policennummer</span>
                <span className="font-mono">{insurance.policyNumber}</span>
              </div>
            )}
            {insurance.startDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Vertragsbeginn</span>
                <span>{new Date(insurance.startDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
            {insurance.endDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Vertragsende</span>
                <span>{new Date(insurance.endDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
            {insurance.cancellationPeriod !== undefined && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kündigungsfrist</span>
                <span>{insurance.cancellationPeriod} Monate</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Premium Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Euro className="h-5 w-5" />
              Beiträge
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {insurance.premium !== undefined && insurance.premium !== null && (
              <div className="text-center py-4">
                <p className="text-3xl font-bold">
                  {insurance.premium.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                </p>
                <p className="text-sm text-muted-foreground">
                  {PREMIUM_INTERVAL_LABELS[insurance.premiumInterval || ''] || insurance.premiumInterval || 'pro Periode'}
                </p>
              </div>
            )}
            {insurance.annualCost !== undefined && insurance.annualCost !== null && (
              <>
                <Separator />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Jährliche Kosten</span>
                  <span className="font-medium">{insurance.annualCost.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Coverage Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Leistungen
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {insurance.coverageAmount !== undefined && insurance.coverageAmount !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Versicherungssumme</span>
                <span className="font-medium">{insurance.coverageAmount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
              </div>
            )}
            {insurance.deductible !== undefined && insurance.deductible !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Selbstbeteiligung</span>
                <span>{insurance.deductible.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
              </div>
            )}
            {insurance.upcomingPayment && (
              <>
                <Separator />
                <div className="flex items-center gap-2 text-sm">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Nächste Zahlung:</span>
                  <span>{new Date(insurance.upcomingPayment).toLocaleDateString('de-DE')}</span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Notes Section */}
      {insurance.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notizen</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{insurance.notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Edit Dialog */}
      <InsuranceEditDialog
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        insurance={insurance}
        onSubmit={handleEdit}
        isLoading={isUpdating}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Versicherung löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Versicherung "{insurance.name}" wirklich löschen?
              Alle zugehörigen Dokumente werden ebenfalls gelöscht.
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

export default InsuranceDetailPage;
