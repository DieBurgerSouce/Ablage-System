/**
 * RecurringSollIst Component
 *
 * Soll/Ist-Vergleichsbericht für wiederkehrende Rechnungen.
 * Zeigt erwartete vs. tatsaechliche Beträge pro Monat.
 */

import { useState } from 'react';
import { BarChart3, CheckCircle, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSollIstReport } from '../hooks/useRecurringInvoices';

// ==================== Helpers ====================

function formatEUR(amount: number | null): string {
  if (amount === null || amount === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDeviation(deviation: number | null): string {
  if (deviation === null || deviation === undefined) return '-';
  const prefix = deviation > 0 ? '+' : '';
  return `${prefix}${new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(deviation)}`;
}

function formatPercent(value: number | null): string {
  if (value === null || value === undefined) return '-';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(1)}%`;
}

const MONTH_NAMES = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
];

// ==================== Component ====================

export default function RecurringSollIst() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const { data: report, isLoading } = useSollIstReport(year, month);

  // Jahr-Optionen: aktuelles Jahr und 2 zurück
  const yearOptions = Array.from({ length: 3 }, (_, i) => now.getFullYear() - i);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4" />
              Soll/Ist-Vergleich
            </CardTitle>
            <CardDescription>
              Erwartete vs. tatsaechliche Abo-Kosten
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={String(month)}
              onValueChange={(val) => setMonth(Number(val))}
            >
              <SelectTrigger className="w-[160px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MONTH_NAMES.map((name, idx) => (
                  <SelectItem key={idx + 1} value={String(idx + 1)}>
                    {name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={String(year)}
              onValueChange={(val) => setYear(Number(val))}
            >
              <SelectTrigger className="w-[100px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {yearOptions.map((y) => (
                  <SelectItem key={y} value={String(y)}>
                    {y}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : report && report.rows.length > 0 ? (
          <>
            {/* Zusammenfassung */}
            <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Soll gesamt</p>
                  <p className="text-lg font-bold">{formatEUR(report.total_expected)}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Ist gesamt</p>
                  <p className="text-lg font-bold">{formatEUR(report.total_actual)}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Abweichung</p>
                  <p
                    className={`text-lg font-bold ${
                      report.total_deviation > 0
                        ? 'text-red-600'
                        : report.total_deviation < 0
                          ? 'text-green-600'
                          : ''
                    }`}
                  >
                    {formatDeviation(report.total_deviation)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-4">
                    <div>
                      <p className="text-sm text-muted-foreground">Zugeordnet</p>
                      <p className="flex items-center gap-1 text-lg font-bold text-green-600">
                        <CheckCircle className="h-4 w-4" />
                        {report.matched_count}
                      </p>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Fehlend</p>
                      <p className="flex items-center gap-1 text-lg font-bold text-red-600">
                        <XCircle className="h-4 w-4" />
                        {report.missing_count}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Detail-Tabelle */}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Lieferant</TableHead>
                  <TableHead>Kategorie</TableHead>
                  <TableHead className="text-right">Soll-Betrag</TableHead>
                  <TableHead className="text-right">Ist-Betrag</TableHead>
                  <TableHead className="text-right">Abweichung</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.rows.map((row) => (
                  <TableRow key={row.recurring_invoice_id}>
                    <TableCell className="font-medium">
                      {row.vendor_name}
                    </TableCell>
                    <TableCell>{row.category || '-'}</TableCell>
                    <TableCell className="text-right">
                      {formatEUR(row.expected_amount)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatEUR(row.actual_amount)}
                    </TableCell>
                    <TableCell
                      className={`text-right ${
                        row.deviation !== null && row.deviation !== 0
                          ? row.deviation > 0
                            ? 'text-red-600'
                            : 'text-green-600'
                          : ''
                      }`}
                    >
                      {formatDeviation(row.deviation)}
                      {row.deviation_percent !== null && row.deviation_percent !== 0 && (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({formatPercent(row.deviation_percent)})
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          row.status === 'matched'
                            ? 'default'
                            : row.status === 'missing'
                              ? 'destructive'
                              : 'secondary'
                        }
                      >
                        {row.status === 'matched'
                          ? 'Zugeordnet'
                          : row.status === 'missing'
                            ? 'Fehlend'
                            : row.status === 'expected'
                              ? 'Erwartet'
                              : row.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
              <TableFooter>
                <TableRow>
                  <TableCell colSpan={2} className="font-bold">
                    Gesamt
                  </TableCell>
                  <TableCell className="text-right font-bold">
                    {formatEUR(report.total_expected)}
                  </TableCell>
                  <TableCell className="text-right font-bold">
                    {formatEUR(report.total_actual)}
                  </TableCell>
                  <TableCell
                    className={`text-right font-bold ${
                      report.total_deviation > 0
                        ? 'text-red-600'
                        : report.total_deviation < 0
                          ? 'text-green-600'
                          : ''
                    }`}
                  >
                    {formatDeviation(report.total_deviation)}
                  </TableCell>
                  <TableCell />
                </TableRow>
              </TableFooter>
            </Table>
          </>
        ) : (
          <div className="py-12 text-center text-muted-foreground">
            Keine Daten für {MONTH_NAMES[month - 1]} {year} vorhanden.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
