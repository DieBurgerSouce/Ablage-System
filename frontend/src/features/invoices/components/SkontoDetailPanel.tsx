/**
 * SkontoDetailPanel - Skonto-Verwaltungskomponente
 *
 * Zeigt Skonto-Details einer Rechnung und ermöglicht:
 * - Skonto-Bedingungen bearbeiten
 * - Skonto anwenden (mit Skonto bezahlen)
 * - Skonto-Frist und Ersparnis anzeigen
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import { Pencil, Percent, CheckCircle, Clock, AlertTriangle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UI_LABELS, type InvoiceTrackingResponse } from '../types/invoice-types';
import { formatCurrency, formatDate, formatDaysUntil } from '@/features/banking/utils/format';
import { useUpdateSkonto, useApplySkonto } from '../hooks/use-invoice-queries';
import { useToast } from '@/hooks/use-toast';

interface SkontoDetailPanelProps {
  invoice: InvoiceTrackingResponse;
  className?: string;
}

export function SkontoDetailPanel({ invoice, className }: SkontoDetailPanelProps) {
  const { toast } = useToast();
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editPercentage, setEditPercentage] = useState<string>(
    invoice.skontoPercentage?.toString() ?? ''
  );
  const [editDays, setEditDays] = useState<string>(
    invoice.skontoDays?.toString() ?? ''
  );

  const updateSkonto = useUpdateSkonto();
  const applySkonto = useApplySkonto();

  // Skonto-Status berechnen
  const hasSkontoConfig = invoice.skontoPercentage !== null && invoice.skontoDays !== null;
  const isSkontoUsed = invoice.skontoUsed;
  const isSkontoExpired = invoice.skontoDeadline
    ? new Date(invoice.skontoDeadline) < new Date()
    : false;
  const isSkontoAvailable = hasSkontoConfig && !isSkontoUsed && !isSkontoExpired;

  // Tage bis Skonto-Frist
  const daysUntilDeadline = invoice.skontoDeadline
    ? Math.ceil(
        (new Date(invoice.skontoDeadline).getTime() - new Date().getTime()) /
          (1000 * 60 * 60 * 24)
      )
    : null;

  const isUrgent = daysUntilDeadline !== null && daysUntilDeadline <= 3 && daysUntilDeadline >= 0;

  // Handler
  const handleSaveSkonto = async () => {
    const percentage = editPercentage ? parseFloat(editPercentage) : undefined;
    const days = editDays ? parseInt(editDays, 10) : undefined;

    if (!percentage && !days) {
      toast({
        title: 'Fehler',
        description: 'Bitte mindestens Prozent oder Tage angeben',
        variant: 'destructive',
      });
      return;
    }

    try {
      await updateSkonto.mutateAsync({
        invoiceId: invoice.id,
        data: { percentage, days },
      });
      toast({
        title: 'Erfolg',
        description: UI_LABELS.successUpdateSkonto,
      });
      setIsEditDialogOpen(false);
    } catch {
      toast({
        title: 'Fehler',
        description: UI_LABELS.errorUpdateSkonto,
        variant: 'destructive',
      });
    }
  };

  const handleApplySkonto = async () => {
    try {
      await applySkonto.mutateAsync(invoice.id);
      toast({
        title: 'Erfolg',
        description: UI_LABELS.successApplySkonto,
      });
    } catch {
      toast({
        title: 'Fehler',
        description: UI_LABELS.errorApplySkonto,
        variant: 'destructive',
      });
    }
  };

  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Percent className="w-4 h-4" />
              {UI_LABELS.skontoTitle}
            </CardTitle>
            <CardDescription>
              {hasSkontoConfig
                ? `${invoice.skontoPercentage}% in ${invoice.skontoDays} Tagen`
                : UI_LABELS.skontoNotConfigured}
            </CardDescription>
          </div>
          <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm">
                <Pencil className="w-4 h-4 mr-1" />
                {UI_LABELS.skontoEdit}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{UI_LABELS.skontoEdit}</DialogTitle>
                <DialogDescription>
                  Skonto-Bedingungen für diese Rechnung festlegen oder ändern.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="skonto-percentage">{UI_LABELS.skontoPercentage}</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="skonto-percentage"
                      type="number"
                      step="0.1"
                      min="0"
                      max="100"
                      value={editPercentage}
                      onChange={(e) => setEditPercentage(e.target.value)}
                      placeholder="z.B. 2"
                    />
                    <span className="text-muted-foreground">%</span>
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="skonto-days">{UI_LABELS.skontoDays}</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="skonto-days"
                      type="number"
                      min="1"
                      max="365"
                      value={editDays}
                      onChange={(e) => setEditDays(e.target.value)}
                      placeholder="z.B. 14"
                    />
                    <span className="text-muted-foreground">Tage</span>
                  </div>
                </div>
                {editPercentage && editDays && invoice.amount && (
                  <div className="p-3 bg-muted rounded-md">
                    <div className="text-sm text-muted-foreground">
                      Vorschau: Bei {editPercentage}% Skonto sparen Sie
                    </div>
                    <div className="text-lg font-semibold text-green-600">
                      {formatCurrency(
                        invoice.amount * (parseFloat(editPercentage) / 100)
                      )}
                    </div>
                  </div>
                )}
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setIsEditDialogOpen(false)}
                >
                  Abbrechen
                </Button>
                <Button
                  onClick={handleSaveSkonto}
                  disabled={updateSkonto.isPending}
                >
                  {updateSkonto.isPending && (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  )}
                  Speichern
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Skonto-Status */}
        {isSkontoUsed && (
          <div className="flex items-center gap-2 p-3 bg-blue-50 text-blue-700 rounded-md">
            <CheckCircle className="w-5 h-5" />
            <div>
              <div className="font-medium">{UI_LABELS.skontoUsed}</div>
              <div className="text-sm">
                Ersparnis: {formatCurrency(invoice.skontoAmount ?? 0)}
              </div>
            </div>
          </div>
        )}

        {isSkontoExpired && !isSkontoUsed && (
          <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-md">
            <AlertTriangle className="w-5 h-5" />
            <div>
              <div className="font-medium">{UI_LABELS.skontoExpired}</div>
              <div className="text-sm">
                Frist war am {formatDate(invoice.skontoDeadline)}
              </div>
            </div>
          </div>
        )}

        {isSkontoAvailable && (
          <div
            className={cn(
              'flex items-center gap-2 p-3 rounded-md',
              isUrgent
                ? 'bg-yellow-50 text-yellow-700'
                : 'bg-green-50 text-green-700'
            )}
          >
            <Clock className="w-5 h-5" />
            <div className="flex-1">
              <div className="font-medium">
                {isUrgent ? UI_LABELS.skontoExpiring : UI_LABELS.skontoAvailable}
              </div>
              <div className="text-sm">
                Noch {formatDaysUntil(daysUntilDeadline ?? 0)} bis{' '}
                {formatDate(invoice.skontoDeadline)}
              </div>
            </div>
          </div>
        )}

        {/* Skonto-Details */}
        {hasSkontoConfig && (
          <>
            <Separator />
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-muted-foreground">{UI_LABELS.skontoPercentage}</div>
                <div className="font-medium">{invoice.skontoPercentage}%</div>
              </div>
              <div>
                <div className="text-muted-foreground">{UI_LABELS.skontoDays}</div>
                <div className="font-medium">{invoice.skontoDays} Tage</div>
              </div>
              <div>
                <div className="text-muted-foreground">{UI_LABELS.skontoDeadline}</div>
                <div className="font-medium">{formatDate(invoice.skontoDeadline)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">{UI_LABELS.skontoSavings}</div>
                <div className="font-medium text-green-600">
                  {formatCurrency(invoice.skontoAmount ?? 0)}
                </div>
              </div>
            </div>
          </>
        )}

        {/* Netto-Betrag bei Skonto */}
        {hasSkontoConfig && !isSkontoUsed && !isSkontoExpired && (
          <>
            <Separator />
            <div className="flex items-center justify-between p-3 bg-muted rounded-md">
              <div>
                <div className="text-sm text-muted-foreground">
                  Zu zahlen bei Skonto-Nutzung
                </div>
                <div className="text-xl font-bold">
                  {formatCurrency(invoice.amount - (invoice.skontoAmount ?? 0))}
                </div>
                <div className="text-xs text-muted-foreground">
                  statt {formatCurrency(invoice.amount)}
                </div>
              </div>
              <Button
                onClick={handleApplySkonto}
                disabled={applySkonto.isPending}
                className="bg-green-600 hover:bg-green-700"
              >
                {applySkonto.isPending && (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                )}
                {UI_LABELS.actionApplySkonto}
              </Button>
            </div>
          </>
        )}

        {/* Kein Skonto konfiguriert */}
        {!hasSkontoConfig && (
          <div className="text-center py-4 text-muted-foreground">
            <Percent className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>{UI_LABELS.skontoNotConfigured}</p>
            <p className="text-xs mt-1">
              Klicken Sie auf &quot;{UI_LABELS.skontoEdit}&quot;, um Skonto hinzuzufuegen.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
