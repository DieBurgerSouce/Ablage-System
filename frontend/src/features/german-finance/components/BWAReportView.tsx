/**
 * BWAReportView Component
 *
 * BWA (Business Report) display with sections
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
import { Printer, TrendingUp, TrendingDown } from 'lucide-react';
import type { BWAReport } from '../types/german-finance-types';
import { UI_LABELS } from '../types/german-finance-types';

interface BWAReportViewProps {
  report: BWAReport;
  onPrint?: () => void;
}

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
};

const formatPercent = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
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

export function BWAReportView({ report, onPrint }: BWAReportViewProps) {
  const handlePrint = () => {
    if (onPrint) {
      onPrint();
    } else {
      window.print();
    }
  };

  const isProfitable = report.profit > 0;

  return (
    <Card className="print:shadow-none">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{UI_LABELS.bwa.title}</CardTitle>
            <CardDescription>{formatPeriod(report.year, report.month)}</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono">
              {report.schema.toUpperCase()}
            </Badge>
            <Badge variant={report.status === 'final' ? 'default' : 'secondary'}>
              {UI_LABELS.bwa.status[report.status]}
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
            <span className="text-muted-foreground">Kontenrahmen:</span>
            <span className="font-medium">{report.schema.toUpperCase()}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Erstellt am:</span>
            <span className="font-medium">{formatDate(report.createdAt)}</span>
          </div>
        </div>

        <Separator />

        {/* Key Metrics */}
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border p-4">
            <div className="text-sm font-medium text-muted-foreground">
              {UI_LABELS.bwa.revenue}
            </div>
            <div className="mt-2 text-2xl font-bold text-green-600">
              {formatEuro(report.revenue)}
            </div>
          </div>
          <div className="rounded-lg border p-4">
            <div className="text-sm font-medium text-muted-foreground">
              {UI_LABELS.bwa.expenses}
            </div>
            <div className="mt-2 text-2xl font-bold text-red-600">
              {formatEuro(report.expenses)}
            </div>
          </div>
          <div className="rounded-lg border p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-muted-foreground">
                {UI_LABELS.bwa.profit}
              </div>
              {isProfitable ? (
                <TrendingUp className="h-5 w-5 text-green-600" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-600" />
              )}
            </div>
            <div
              className={`mt-2 text-2xl font-bold ${
                isProfitable ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {formatEuro(report.profit)}
            </div>
          </div>
        </div>

        <Separator />

        {/* BWA Sections Table */}
        <div>
          <h3 className="mb-4 text-sm font-semibold">Detaillierte Auswertung</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60%]">Position</TableHead>
                <TableHead className="text-right">Betrag</TableHead>
                <TableHead className="text-right">Anteil</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.sections.map((section, index) => {
                const isRevenue = section.name.toLowerCase().includes('erlös') ||
                                  section.name.toLowerCase().includes('umsatz');
                const isProfit = section.name.toLowerCase().includes('ergebnis');

                return (
                  <TableRow
                    key={index}
                    className={isProfit ? 'border-t-2 bg-muted/50' : ''}
                  >
                    <TableCell className={isProfit ? 'font-bold' : 'font-medium'}>
                      {section.name}
                    </TableCell>
                    <TableCell
                      className={`text-right ${isProfit ? 'font-bold' : ''} ${
                        isRevenue ? 'text-green-600' : section.amount < 0 ? 'text-red-600' : ''
                      }`}
                    >
                      {formatEuro(section.amount)}
                    </TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground">
                      {section.percentage !== null ? formatPercent(section.percentage) : '-'}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>

        {/* Footer Info */}
        <div className="text-xs text-muted-foreground print:block">
          <p>BWA ID: {report.id}</p>
          <p className="mt-1">
            Erstellt mit Ablage-System am {formatDate(report.createdAt)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
