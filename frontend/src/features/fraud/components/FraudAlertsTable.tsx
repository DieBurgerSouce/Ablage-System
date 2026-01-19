/**
 * Fraud Alerts Table
 *
 * Zeigt Fraud-Alerts mit Filterung und Details.
 */

import { useState } from 'react';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertTriangle,
  ShieldAlert,
  Eye,
  ExternalLink,
} from 'lucide-react';
import type { FraudAlert } from '../api/fraud-api';

interface FraudAlertsTableProps {
  alerts: FraudAlert[];
  onViewInvoice?: (invoiceId: string) => void;
  onViewEntity?: (entityId: string) => void;
}

const riskBadgeConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  critical: { label: 'Kritisch', variant: 'destructive' },
  high: { label: 'Hoch', variant: 'destructive' },
  medium: { label: 'Mittel', variant: 'default' },
  low: { label: 'Niedrig', variant: 'secondary' },
};

const fraudTypeLabels: Record<string, string> = {
  duplicate_invoice: 'Duplikat',
  price_anomaly: 'Preis-Anomalie',
  phantom_supplier: 'Phantom-Lieferant',
  expense_fraud: 'Spesen-Betrug',
  kickback: 'Kickback',
  shell_company: 'Shell-Company',
  round_amount: 'Runde Betraege',
  split_invoice: 'Invoice-Splitting',
  weekend_invoice: 'Wochenend-Rechnung',
};

export function FraudAlertsTable({
  alerts,
  onViewInvoice,
  onViewEntity,
}: FraudAlertsTableProps) {
  const [selectedAlert, setSelectedAlert] = useState<FraudAlert | null>(null);

  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(value);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (alerts.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5" />
            Fraud-Alerts
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <ShieldAlert className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine verdaechtigen Aktivitaeten erkannt</p>
            <p className="text-sm">Alle Transaktionen sind unauffaellig</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Gruppiere nach Risikostufe
  const criticalCount = alerts.filter(a => a.risk_level === 'critical').length;
  const highCount = alerts.filter(a => a.risk_level === 'high').length;

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5" />
                Fraud-Alerts
              </CardTitle>
              <CardDescription>
                {alerts.length} Alerts gefunden
                {criticalCount > 0 && ` (${criticalCount} kritisch)`}
                {highCount > 0 && `, ${highCount} hoch`}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Risiko</TableHead>
                <TableHead>Typ</TableHead>
                <TableHead>Beschreibung</TableHead>
                <TableHead className="text-right">Betrag</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Erkannt</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {alerts.map((alert, index) => {
                const risk = riskBadgeConfig[alert.risk_level] || riskBadgeConfig.low;
                const typeLabel = fraudTypeLabels[alert.type] || alert.type;

                return (
                  <TableRow key={index}>
                    <TableCell>
                      <Badge variant={risk.variant}>{risk.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm font-medium">{typeLabel}</span>
                    </TableCell>
                    <TableCell className="max-w-[300px]">
                      <div className="truncate" title={alert.description}>
                        {alert.title}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      {alert.amount ? formatCurrency(alert.amount) : '-'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-12 h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              alert.confidence >= 0.8
                                ? 'bg-green-500'
                                : alert.confidence >= 0.6
                                ? 'bg-amber-500'
                                : 'bg-red-500'
                            }`}
                            style={{ width: `${alert.confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {(alert.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground">
                        {formatDate(alert.detected_at)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedAlert(alert)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={!!selectedAlert} onOpenChange={() => setSelectedAlert(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              {selectedAlert?.title}
            </DialogTitle>
            <DialogDescription>
              {selectedAlert && fraudTypeLabels[selectedAlert.type]}
            </DialogDescription>
          </DialogHeader>

          {selectedAlert && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant={riskBadgeConfig[selectedAlert.risk_level]?.variant}>
                  {riskBadgeConfig[selectedAlert.risk_level]?.label}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  Confidence: {(selectedAlert.confidence * 100).toFixed(0)}%
                </span>
              </div>

              <div className="prose dark:prose-invert max-w-none">
                <p>{selectedAlert.description}</p>
              </div>

              {selectedAlert.amount && (
                <div className="p-4 bg-slate-50 dark:bg-slate-900 rounded-lg">
                  <p className="text-sm text-muted-foreground">Betroffener Betrag</p>
                  <p className="text-2xl font-bold">
                    {formatCurrency(selectedAlert.amount)}
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4 text-sm">
                {selectedAlert.entity_name && (
                  <div>
                    <p className="text-muted-foreground">Entity</p>
                    <p className="font-medium">{selectedAlert.entity_name}</p>
                  </div>
                )}
                <div>
                  <p className="text-muted-foreground">Erkannt am</p>
                  <p className="font-medium">{formatDate(selectedAlert.detected_at)}</p>
                </div>
              </div>

              <div className="flex gap-2 pt-4 border-t">
                {selectedAlert.invoice_id && onViewInvoice && (
                  <Button
                    variant="outline"
                    onClick={() => onViewInvoice(selectedAlert.invoice_id!)}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Rechnung ansehen
                  </Button>
                )}
                {selectedAlert.entity_id && onViewEntity && (
                  <Button
                    variant="outline"
                    onClick={() => onViewEntity(selectedAlert.entity_id!)}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Entity ansehen
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
