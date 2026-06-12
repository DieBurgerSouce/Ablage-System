/**
 * DiscrepancyPanel - Abweichungs-Verwaltungskomponente
 *
 * Zeigt Abweichungen einer Auftragskette und ermöglicht:
 * - Abweichungen auflisten
 * - Abweichungen auflösen
 * - Differenzen anzeigen
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  AlertTriangle,
  CheckCircle,
  Info,
  ArrowRight,
  Loader2,
  FileText,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  type ChainDiscrepancy,
  type DiscrepancySeverity,
  type DiscrepancyType,
  CHAIN_UI_LABELS,
  DISCREPANCY_SEVERITY_STYLES,
} from '../types/chain-types';
import { formatDateTime } from '@/features/banking/utils/format';
import { useResolveDiscrepancy } from '../hooks/use-chain-queries';
import { useToast } from '@/hooks/use-toast';

interface DiscrepancyPanelProps {
  chainId: string;
  discrepancies: ChainDiscrepancy[];
  className?: string;
}

const DISCREPANCY_TYPE_LABELS: Record<DiscrepancyType, string> = {
  amount: CHAIN_UI_LABELS.discrepancyAmount,
  quantity: CHAIN_UI_LABELS.discrepancyQuantity,
  item: CHAIN_UI_LABELS.discrepancyItem,
  date: CHAIN_UI_LABELS.discrepancyDate,
  other: CHAIN_UI_LABELS.discrepancyOther,
};

const SEVERITY_ICONS: Record<DiscrepancySeverity, typeof AlertTriangle> = {
  info: Info,
  warning: AlertTriangle,
  error: AlertTriangle,
};

export function DiscrepancyPanel({
  chainId,
  discrepancies,
  className,
}: DiscrepancyPanelProps) {
  const { toast } = useToast();
  const [selectedDiscrepancy, setSelectedDiscrepancy] = useState<ChainDiscrepancy | null>(
    null
  );
  const [resolutionNotes, setResolutionNotes] = useState('');
  const resolveDiscrepancy = useResolveDiscrepancy();

  const unresolvedDiscrepancies = discrepancies.filter((d) => !d.isResolved);
  const resolvedDiscrepancies = discrepancies.filter((d) => d.isResolved);

  const handleResolve = async () => {
    if (!selectedDiscrepancy) return;

    if (!resolutionNotes.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Loesungshinweis ein',
        variant: 'destructive',
      });
      return;
    }

    try {
      await resolveDiscrepancy.mutateAsync({
        discrepancyId: selectedDiscrepancy.id,
        chainId,
        data: { resolutionNotes: resolutionNotes.trim() },
      });
      toast({
        title: 'Erfolg',
        description: CHAIN_UI_LABELS.successResolveDiscrepancy,
      });
      setSelectedDiscrepancy(null);
      setResolutionNotes('');
    } catch {
      toast({
        title: 'Fehler',
        description: CHAIN_UI_LABELS.errorResolveDiscrepancy,
        variant: 'destructive',
      });
    }
  };

  return (
    <>
      <Card className={cn('', className)}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="w-4 h-4" />
                Abweichungen
              </CardTitle>
              <CardDescription>
                {unresolvedDiscrepancies.length === 0
                  ? CHAIN_UI_LABELS.emptyNoDiscrepancies
                  : `${unresolvedDiscrepancies.length} offene Abweichung(en)`}
              </CardDescription>
            </div>
            {unresolvedDiscrepancies.length > 0 && (
              <Badge
                variant="outline"
                className="bg-yellow-50 text-yellow-700 border-yellow-200"
              >
                {unresolvedDiscrepancies.length} offen
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Offene Abweichungen */}
          {unresolvedDiscrepancies.length > 0 && (
            <div className="space-y-2">
              {unresolvedDiscrepancies.map((disc) => (
                <DiscrepancyItem
                  key={disc.id}
                  discrepancy={disc}
                  onResolve={() => setSelectedDiscrepancy(disc)}
                />
              ))}
            </div>
          )}

          {/* Aufgelöste Abweichungen (eingeklappt) */}
          {resolvedDiscrepancies.length > 0 && (
            <>
              <Separator />
              <Accordion type="single" collapsible>
                <AccordionItem value="resolved" className="border-0">
                  <AccordionTrigger className="py-2 hover:no-underline">
                    <span className="flex items-center gap-2 text-sm text-muted-foreground">
                      <CheckCircle className="w-4 h-4" />
                      {resolvedDiscrepancies.length} aufgelöst
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2 pt-2">
                      {resolvedDiscrepancies.map((disc) => (
                        <DiscrepancyItem
                          key={disc.id}
                          discrepancy={disc}
                          isResolved
                        />
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </>
          )}

          {/* Keine Abweichungen */}
          {discrepancies.length === 0 && (
            <div className="text-center py-6 text-muted-foreground">
              <CheckCircle className="w-8 h-8 mx-auto mb-2 opacity-50 text-green-500" />
              <p>{CHAIN_UI_LABELS.emptyNoDiscrepancies}</p>
              <p className="text-xs mt-1">
                Alle Dokumente in dieser Kette stimmen überein.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resolve Dialog */}
      <Dialog
        open={!!selectedDiscrepancy}
        onOpenChange={(open) => !open && setSelectedDiscrepancy(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{CHAIN_UI_LABELS.actionResolveDiscrepancy}</DialogTitle>
            <DialogDescription>
              Erklären Sie, wie diese Abweichung behoben wurde.
            </DialogDescription>
          </DialogHeader>

          {selectedDiscrepancy && (
            <div className="space-y-4 py-4">
              {/* Discrepancy Details */}
              <div className="p-3 bg-muted rounded-md space-y-2">
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={cn(
                      'text-xs',
                      DISCREPANCY_SEVERITY_STYLES[selectedDiscrepancy.severity].bgColor,
                      DISCREPANCY_SEVERITY_STYLES[selectedDiscrepancy.severity].textColor,
                      DISCREPANCY_SEVERITY_STYLES[selectedDiscrepancy.severity].borderColor
                    )}
                  >
                    {DISCREPANCY_SEVERITY_STYLES[selectedDiscrepancy.severity].label}
                  </Badge>
                  <span className="text-sm font-medium">
                    {DISCREPANCY_TYPE_LABELS[selectedDiscrepancy.discrepancyType]}
                  </span>
                </div>
                <p className="text-sm">{selectedDiscrepancy.description}</p>
                {selectedDiscrepancy.sourceValue &&
                  selectedDiscrepancy.targetValue && (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">
                        {selectedDiscrepancy.sourceValue}
                      </span>
                      <ArrowRight className="w-4 h-4" />
                      <span className="text-muted-foreground">
                        {selectedDiscrepancy.targetValue}
                      </span>
                      {selectedDiscrepancy.differencePercentage && (
                        <Badge variant="secondary" className="text-xs">
                          {selectedDiscrepancy.differencePercentage.toFixed(1)}%
                        </Badge>
                      )}
                    </div>
                  )}
              </div>

              {/* Resolution Notes */}
              <div className="space-y-2">
                <Label htmlFor="resolution-notes">Loesungshinweis</Label>
                <Textarea
                  id="resolution-notes"
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="z.B. Rabatt nachträglich gewährt, Differenz erklärt..."
                  rows={3}
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedDiscrepancy(null)}>
              Abbrechen
            </Button>
            <Button
              onClick={handleResolve}
              disabled={resolveDiscrepancy.isPending}
              className="bg-green-600 hover:bg-green-700"
            >
              {resolveDiscrepancy.isPending && (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              )}
              Als aufgelöst markieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// Einzelne Abweichung
function DiscrepancyItem({
  discrepancy,
  onResolve,
  isResolved = false,
}: {
  discrepancy: ChainDiscrepancy;
  onResolve?: () => void;
  isResolved?: boolean;
}) {
  const severityStyle = DISCREPANCY_SEVERITY_STYLES[discrepancy.severity];
  const SeverityIcon = SEVERITY_ICONS[discrepancy.severity];

  return (
    <div
      className={cn(
        'p-3 rounded-md border',
        isResolved ? 'bg-muted/50' : severityStyle.bgColor,
        isResolved ? 'border-muted' : severityStyle.borderColor
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <SeverityIcon
            className={cn(
              'w-4 h-4 mt-0.5',
              isResolved ? 'text-muted-foreground' : severityStyle.textColor
            )}
          />
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'text-sm font-medium',
                  isResolved && 'text-muted-foreground line-through'
                )}
              >
                {DISCREPANCY_TYPE_LABELS[discrepancy.discrepancyType]}
              </span>
              {discrepancy.differencePercentage && (
                <Badge variant="secondary" className="text-xs">
                  {discrepancy.differencePercentage.toFixed(1)}%
                </Badge>
              )}
            </div>
            <p
              className={cn(
                'text-sm',
                isResolved ? 'text-muted-foreground' : severityStyle.textColor
              )}
            >
              {discrepancy.description}
            </p>
            {discrepancy.sourceValue && discrepancy.targetValue && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <FileText className="w-3 h-3" />
                <span>{discrepancy.sourceValue}</span>
                <ArrowRight className="w-3 h-3" />
                <span>{discrepancy.targetValue}</span>
              </div>
            )}
            {isResolved && discrepancy.resolutionNotes && (
              <div className="mt-2 p-2 bg-green-50 rounded text-xs text-green-700">
                <div className="font-medium">Aufgelöst:</div>
                <div>{discrepancy.resolutionNotes}</div>
                <div className="text-green-600 mt-1">
                  {formatDateTime(discrepancy.resolvedAt)}
                </div>
              </div>
            )}
          </div>
        </div>
        {!isResolved && onResolve && (
          <Button variant="ghost" size="sm" onClick={onResolve}>
            Auflösen
          </Button>
        )}
      </div>
    </div>
  );
}
