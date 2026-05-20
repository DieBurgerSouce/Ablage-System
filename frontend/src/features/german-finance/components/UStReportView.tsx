/**
 * UStReportView Component
 *
 * Single USt-Voranmeldung report display
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Printer } from 'lucide-react';
import type { UStReport } from '../types/german-finance-types';
import { UI_LABELS } from '../types/german-finance-types';

interface UStReportViewProps {
  report: UStReport;
  onPrint?: () => void;
}

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
};

const formatDate = (date: Date): string => {
  return date.toLocaleDateString('de-DE', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};

const formatPeriod = (year: number, month: number): string => {
  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
  ];
  return `${monthNames[month - 1]} ${year}`;
};

const getStatusVariant = (status: UStReport['status']): 'default' | 'secondary' | 'outline' => {
  switch (status) {
    case 'approved':
      return 'default';
    case 'submitted':
      return 'secondary';
    case 'draft':
    default:
      return 'outline';
  }
};

export function UStReportView({ report, onPrint }: UStReportViewProps) {
  const handlePrint = () => {
    if (onPrint) {
      onPrint();
    } else {
      window.print();
    }
  };

  return (
    <Card className="print:shadow-none">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{UI_LABELS.ust.title}</CardTitle>
            <CardDescription>{formatPeriod(report.year, report.month)}</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={getStatusVariant(report.status)}>
              {UI_LABELS.ust.status[report.status]}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrint}
              className="print:hidden"
            >
              <Printer className="mr-2 h-4 w-4" />
              {UI_LABELS.common.print}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Summary Info */}
        <div className="grid gap-4 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Erstellt am:</span>
            <span className="font-medium">{formatDate(report.createdAt)}</span>
          </div>
          {report.submittedAt && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">Eingereicht am:</span>
              <span className="font-medium">{formatDate(report.submittedAt)}</span>
            </div>
          )}
        </div>

        <Separator />

        {/* USt Details Table */}
        <div>
          <h3 className="mb-4 text-sm font-semibold">Umsatzsteuerberechnung</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60%]">Position</TableHead>
                <TableHead className="text-right">Betrag</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium">{UI_LABELS.ust.umsatzsteuer19}</TableCell>
                <TableCell className="text-right">{formatEuro(report.umsatzsteuer19)}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">{UI_LABELS.ust.umsatzsteuer7}</TableCell>
                <TableCell className="text-right">{formatEuro(report.umsatzsteuer7)}</TableCell>
              </TableRow>
              {report.umsatzsteuer0 > 0 && (
                <TableRow>
                  <TableCell className="font-medium">{UI_LABELS.ust.umsatzsteuer0}</TableCell>
                  <TableCell className="text-right">{formatEuro(report.umsatzsteuer0)}</TableCell>
                </TableRow>
              )}
              <TableRow className="border-t-2">
                <TableCell className="font-semibold">{UI_LABELS.ust.umsatzsteuer}</TableCell>
                <TableCell className="text-right font-semibold">
                  {formatEuro(report.umsatzsteuer)}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-medium">{UI_LABELS.ust.vorsteuer}</TableCell>
                <TableCell className="text-right">{formatEuro(report.vorsteuer)}</TableCell>
              </TableRow>
              <TableRow className="border-t-2 bg-muted/50">
                <TableCell className="text-lg font-bold">{UI_LABELS.ust.zahllast}</TableCell>
                <TableCell className="text-right text-lg font-bold">
                  {formatEuro(report.zahllast)}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        {/* Notes */}
        {report.notes && (
          <>
            <Separator />
            <div>
              <h3 className="mb-2 text-sm font-semibold">Hinweise</h3>
              <p className="text-sm text-muted-foreground">{report.notes}</p>
            </div>
          </>
        )}

        {/* Footer Info */}
        <div className="text-xs text-muted-foreground print:block">
          <p>USt-Voranmeldung ID: {report.id}</p>
          <p className="mt-1">
            Erstellt mit Ablage-System am {formatDate(report.createdAt)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
