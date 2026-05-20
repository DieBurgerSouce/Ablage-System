/**
 * PaymentPredictions - Zahlungsvorhersage-Tabelle
 *
 * Zeigt KI-basierte Zahlungsvorhersagen mit:
 * - Erwartetes Zahlungsdatum
 * - Konfidenz-Indikator
 * - Verzoegerungsrisiko-Badge
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, Calendar } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePaymentPredictions } from '../hooks/use-predictions';

function getRiskBadge(delayProbability: number) {
  if (delayProbability > 0.7) {
    return (
      <Badge variant="destructive" className="text-xs">
        Hoch
      </Badge>
    );
  }
  if (delayProbability > 0.3) {
    return <Badge className="text-xs bg-amber-500">Mittel</Badge>;
  }
  return (
    <Badge variant="secondary" className="text-xs">
      Niedrig
    </Badge>
  );
}

export function PaymentPredictions() {
  const { data: predictions, isLoading, isError } = usePaymentPredictions();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Lade Zahlungsvorhersagen...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError || !predictions) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          Zahlungsvorhersagen nicht verfuegbar
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Calendar className="h-5 w-5" />
          Zahlungsvorhersagen
          <Badge variant="outline" className="text-xs ml-auto">
            {predictions.length} Rechnungen
          </Badge>
        </CardTitle>
      </CardHeader>

      <CardContent>
        {predictions.length === 0 ? (
          <div className="text-center py-6 text-muted-foreground text-sm">
            Keine offenen Zahlungsvorhersagen
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="text-left py-2 font-medium">Entitaet</th>
                  <th className="text-left py-2 font-medium">Erw. Zahlung</th>
                  <th className="text-center py-2 font-medium">
                    Wahrscheinlichkeit
                  </th>
                  <th className="text-center py-2 font-medium">Risiko</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {predictions.map((prediction) => (
                  <tr
                    key={prediction.invoice_id}
                    className="hover:bg-muted/50"
                  >
                    <td className="py-2.5">
                      <div className="font-medium text-xs">
                        {prediction.entity_name ||
                          prediction.invoice_id.slice(0, 8)}
                      </div>
                    </td>
                    <td className="py-2.5 text-xs">
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3 text-muted-foreground" />
                        {new Date(
                          prediction.predicted_date,
                        ).toLocaleDateString('de-DE')}
                        <span className="text-muted-foreground">
                          ({prediction.predicted_days} Tage)
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div
                            className={cn(
                              'h-full rounded-full',
                              prediction.confidence > 0.7
                                ? 'bg-green-500'
                                : prediction.confidence > 0.4
                                  ? 'bg-amber-500'
                                  : 'bg-red-500',
                            )}
                            style={{
                              width: `${prediction.confidence * 100}%`,
                            }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground w-10">
                          {(prediction.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 text-center">
                      {getRiskBadge(prediction.delay_probability)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
