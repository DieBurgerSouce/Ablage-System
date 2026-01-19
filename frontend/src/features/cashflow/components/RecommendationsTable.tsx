/**
 * Payment Recommendations Table
 *
 * Zeigt Zahlungsempfehlungen mit Priorisierung und Skonto-Hinweisen.
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, Clock, Euro, Sparkles } from 'lucide-react';
import type { PaymentRecommendation } from '../api/cashflow-api';

interface RecommendationsTableProps {
  recommendations: PaymentRecommendation[];
  onPayInvoice?: (invoiceId: string) => void;
}

const urgencyConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  overdue: { label: 'Ueberfaellig', variant: 'destructive' },
  critical: { label: 'Kritisch', variant: 'destructive' },
  high: { label: 'Hoch', variant: 'default' },
  medium: { label: 'Mittel', variant: 'secondary' },
  low: { label: 'Niedrig', variant: 'outline' },
};

export function RecommendationsTable({
  recommendations,
  onPayInvoice,
}: RecommendationsTableProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(value);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE');
  };

  if (recommendations.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Zahlungsempfehlungen
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            Keine offenen Zahlungen vorhanden
          </div>
        </CardContent>
      </Card>
    );
  }

  // Statistiken
  const totalAmount = recommendations.reduce((sum, r) => sum + r.amount, 0);
  const totalSkontoSavings = recommendations.reduce((sum, r) => sum + r.skonto_savings, 0);
  const urgentCount = recommendations.filter(
    (r) => r.urgency === 'critical' || r.urgency === 'overdue'
  ).length;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" />
              Zahlungsempfehlungen
            </CardTitle>
            <CardDescription>
              {recommendations.length} offene Zahlungen, Gesamtsumme:{' '}
              {formatCurrency(totalAmount)}
            </CardDescription>
          </div>
          <div className="flex items-center gap-4 text-sm">
            {urgentCount > 0 && (
              <div className="flex items-center gap-1 text-destructive">
                <AlertTriangle className="h-4 w-4" />
                {urgentCount} dringend
              </div>
            )}
            {totalSkontoSavings > 0 && (
              <div className="flex items-center gap-1 text-green-600">
                <Euro className="h-4 w-4" />
                {formatCurrency(totalSkontoSavings)} Skonto moeglich
              </div>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Rechnung</TableHead>
              <TableHead>Betrag</TableHead>
              <TableHead>Faellig</TableHead>
              <TableHead>Prioritaet</TableHead>
              <TableHead>Empfehlung</TableHead>
              <TableHead>Skonto</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {recommendations.map((rec) => {
              const urgency = urgencyConfig[rec.urgency] || urgencyConfig.low;

              return (
                <TableRow key={rec.invoice_id}>
                  <TableCell className="font-medium">
                    {rec.invoice_number || rec.invoice_id.slice(0, 8)}
                  </TableCell>
                  <TableCell>{formatCurrency(rec.amount)}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      {rec.days_until_due < 0 ? (
                        <span className="text-destructive font-medium">
                          {Math.abs(rec.days_until_due)} Tage ueberfaellig
                        </span>
                      ) : (
                        <>
                          <Clock className="h-3 w-3" />
                          <span>{formatDate(rec.due_date)}</span>
                          <span className="text-muted-foreground text-xs">
                            ({rec.days_until_due}d)
                          </span>
                        </>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={urgency.variant}>{urgency.label}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{rec.reason || '-'}</span>
                  </TableCell>
                  <TableCell>
                    {rec.skonto_savings > 0 ? (
                      <div className="text-green-600 text-sm">
                        <div className="font-medium">
                          {formatCurrency(rec.skonto_savings)}
                        </div>
                        {rec.skonto_deadline && (
                          <div className="text-xs">
                            bis {formatDate(rec.skonto_deadline)}
                          </div>
                        )}
                      </div>
                    ) : (
                      '-'
                    )}
                  </TableCell>
                  <TableCell>
                    {onPayInvoice && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onPayInvoice(rec.invoice_id)}
                      >
                        Zahlen
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
