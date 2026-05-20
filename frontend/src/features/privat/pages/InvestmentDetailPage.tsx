/**
 * InvestmentDetailPage - Geldanlage-Detailansicht
 *
 * Zeigt alle Details einer Geldanlage inkl. Renditeübersicht
 */

import * as React from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { ArrowLeft, Edit, Trash2, PiggyBank, Euro, Calendar, TrendingUp, TrendingDown, Loader2 } from 'lucide-react';
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
import type { PrivatInvestmentWithStats, PrivatInvestmentUpdate } from '@/types/privat';
import { InvestmentEditDialog } from '../components/finances/InvestmentEditDialog';

const INVESTMENT_TYPE_LABELS: Record<string, string> = {
  savings: 'Sparkonto/Tagesgeld',
  stocks: 'Aktien',
  bonds: 'Anleihen',
  fund: 'Fonds',
  etf: 'ETF',
  real_estate: 'Immobilienfonds',
  crypto: 'Kryptowährungen',
  pension: 'Altersvorsorge',
  other: 'Sonstiges',
};

export function InvestmentDetailPage() {
  const navigate = useNavigate();
  const { investmentId } = useParams({ strict: false }) as { investmentId: string };

  const [investment, setInvestment] = React.useState<PrivatInvestmentWithStats | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false);
  const [showEditDialog, setShowEditDialog] = React.useState(false);
  const [isUpdating, setIsUpdating] = React.useState(false);

  // Load investment details
  React.useEffect(() => {
    const loadInvestment = async () => {
      if (!investmentId) {
        setError(new Error('Keine Anlage-ID angegeben'));
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const data = await privatApi.getInvestment(investmentId);
        setInvestment(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden der Geldanlage'));
      } finally {
        setIsLoading(false);
      }
    };
    loadInvestment();
  }, [investmentId]);

  const handleEdit = async (invId: string, data: PrivatInvestmentUpdate) => {
    setIsUpdating(true);
    try {
      const updated = await privatApi.updateInvestment(invId, data);
      setInvestment(updated);
      toast.success('Geldanlage aktualisiert');
    } catch (err) {
      toast.error('Fehler beim Aktualisieren');
      throw err;
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!investment) return;

    try {
      await privatApi.deleteInvestment(investment.id);
      toast.success('Geldanlage gelöscht');
      navigate({ to: '/privat/finanzen' });
    } catch (err) {
      toast.error('Fehler beim Löschen der Geldanlage');
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

  if (error || !investment) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <p className="text-destructive mb-4">{error?.message || 'Geldanlage nicht gefunden'}</p>
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    );
  }

  const isPositiveReturn = investment.totalReturn >= 0;

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{investment.name}</h1>
            <p className="text-muted-foreground">
              {INVESTMENT_TYPE_LABELS[investment.investmentType] || investment.investmentType}
            </p>
          </div>
          {investment.isTaxable && (
            <Badge variant="secondary">Steuerpflichtig</Badge>
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

      {/* Performance Highlight */}
      <Card className={isPositiveReturn ? 'border-green-500/50' : 'border-red-500/50'}>
        <CardContent className="py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {isPositiveReturn ? (
                <TrendingUp className="h-8 w-8 text-green-500" />
              ) : (
                <TrendingDown className="h-8 w-8 text-red-500" />
              )}
              <div>
                <p className="text-sm text-muted-foreground">Gesamtrendite</p>
                <p className={`text-2xl font-bold ${isPositiveReturn ? 'text-green-600' : 'text-red-600'}`}>
                  {isPositiveReturn ? '+' : ''}{investment.totalReturn.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
                </p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm text-muted-foreground">Prozentual</p>
              <Badge variant={isPositiveReturn ? 'default' : 'destructive'} className="text-lg px-3 py-1">
                {isPositiveReturn ? '+' : ''}{investment.returnPercentage.toFixed(2)}%
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Value Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Euro className="h-5 w-5" />
              Wert
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-center py-4">
              <p className="text-3xl font-bold">
                {investment.currentValue.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
              </p>
              <p className="text-sm text-muted-foreground">Aktueller Wert</p>
            </div>
            <Separator />
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Anlagesumme</span>
              <span>{investment.initialAmount.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Differenz</span>
              <span className={isPositiveReturn ? 'text-green-600' : 'text-red-600'}>
                {isPositiveReturn ? '+' : ''}{investment.totalReturn.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Details Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PiggyBank className="h-5 w-5" />
              Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {investment.institution && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Institut</span>
                <span>{investment.institution}</span>
              </div>
            )}
            {investment.accountNumber && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Kontonummer</span>
                <span className="font-mono">{investment.accountNumber}</span>
              </div>
            )}
            {investment.interestRate !== undefined && investment.interestRate !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Zinssatz/Rendite</span>
                <span>{investment.interestRate.toFixed(2)}%</span>
              </div>
            )}
            {investment.annualReturn !== undefined && investment.annualReturn !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Jahresrendite</span>
                <span className={investment.annualReturn >= 0 ? 'text-green-600' : 'text-red-600'}>
                  {investment.annualReturn >= 0 ? '+' : ''}{investment.annualReturn.toFixed(2)}%
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Dates Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Laufzeit
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {investment.startDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Beginn</span>
                <span>{new Date(investment.startDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
            {investment.maturityDate && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Fälligkeit</span>
                <span>{new Date(investment.maturityDate).toLocaleDateString('de-DE')}</span>
              </div>
            )}
            {investment.startDate && (
              <>
                <Separator />
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Laufzeit</span>
                  <span>
                    {Math.floor((Date.now() - new Date(investment.startDate).getTime()) / (1000 * 60 * 60 * 24 * 30))} Monate
                  </span>
                </div>
              </>
            )}
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Steuerpflichtig</span>
              <Badge variant={investment.isTaxable ? 'secondary' : 'outline'}>
                {investment.isTaxable ? 'Ja' : 'Nein'}
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Notes Section */}
      {investment.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notizen</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap">{investment.notes}</p>
          </CardContent>
        </Card>
      )}

      {/* Edit Dialog */}
      <InvestmentEditDialog
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
        investment={investment}
        onSubmit={handleEdit}
        isLoading={isUpdating}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Geldanlage löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Geldanlage "{investment.name}" wirklich löschen?
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

export default InvestmentDetailPage;
