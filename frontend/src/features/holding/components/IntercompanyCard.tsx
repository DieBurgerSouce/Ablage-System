/**
 * Intercompany Card
 *
 * Zeigt Intercompany-Verrechnungen und Transaktionen.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeftRight, Building2 } from 'lucide-react';
import type { IntercompanyMetrics } from '../api/holding-api';

interface IntercompanyCardProps {
  intercompany: IntercompanyMetrics;
}

export function IntercompanyCard({ intercompany }: IntercompanyCardProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const hasIntercompany = intercompany.transaction_count > 0;

  if (!hasIntercompany) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ArrowLeftRight className="h-5 w-5" />
            Intercompany
          </CardTitle>
          <CardDescription>Transaktionen zwischen Firmen</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
            <Building2 className="h-12 w-12 mb-4 opacity-50" />
            <p>Keine Intercompany-Transaktionen</p>
            <p className="text-sm mt-1">
              Transaktionen zwischen Firmen werden hier angezeigt
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const netPosition = intercompany.intercompany_receivables - intercompany.intercompany_payables;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ArrowLeftRight className="h-5 w-5" />
          Intercompany
        </CardTitle>
        <CardDescription>
          {intercompany.transaction_count} offene Transaktionen zwischen Firmen
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Total Volume */}
        <div className="p-4 rounded-lg bg-muted">
          <div className="text-sm text-muted-foreground">Gesamtvolumen</div>
          <div className="text-2xl font-bold">
            {formatCurrency(intercompany.total_intercompany_volume)}
          </div>
        </div>

        {/* Receivables & Payables */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 rounded-lg border">
            <div className="text-xs text-muted-foreground mb-1">Forderungen</div>
            <div className="text-lg font-medium text-green-600">
              {formatCurrency(intercompany.intercompany_receivables)}
            </div>
          </div>
          <div className="p-3 rounded-lg border">
            <div className="text-xs text-muted-foreground mb-1">Verbindlichkeiten</div>
            <div className="text-lg font-medium text-red-600">
              {formatCurrency(intercompany.intercompany_payables)}
            </div>
          </div>
        </div>

        {/* Net Position */}
        <div className="pt-3 border-t">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Netto-Position (intern)</span>
            <span
              className={`font-medium ${
                netPosition >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {formatCurrency(netPosition)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Diese Beträge werden bei der Konsolidierung eliminiert.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
