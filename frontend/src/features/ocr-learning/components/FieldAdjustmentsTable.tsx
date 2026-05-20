/**
 * Field Adjustments Table Component
 *
 * Zeigt detaillierte Feld-spezifische Confidence-Anpassungen.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import type { LearningStats } from '../api/ocr-learning-api';

interface FieldAdjustmentsTableProps {
  stats: LearningStats;
}

export function FieldAdjustmentsTable({ stats }: FieldAdjustmentsTableProps) {
  // Flatten field adjustments into a table-friendly format
  const fieldData: Array<{
    backend: string;
    field: string;
    adjustment: number;
  }> = [];

  Object.entries(stats.field_adjustments || {}).forEach(([backend, fields]) => {
    Object.entries(fields).forEach(([field, adjustment]) => {
      fieldData.push({ backend, field, adjustment });
    });
  });

  // Sort by absolute adjustment (largest first)
  fieldData.sort((a, b) => Math.abs(b.adjustment) - Math.abs(a.adjustment));

  const getAdjustmentIcon = (adjustment: number) => {
    if (adjustment > 0.01) return <ArrowUp className="w-4 h-4 text-green-500" />;
    if (adjustment < -0.01) return <ArrowDown className="w-4 h-4 text-red-500" />;
    return <Minus className="w-4 h-4 text-muted-foreground" />;
  };

  const getAdjustmentBadge = (adjustment: number) => {
    const percent = (adjustment * 100).toFixed(1);
    if (adjustment > 0.01) {
      return <Badge className="bg-green-500">+{percent}%</Badge>;
    }
    if (adjustment < -0.01) {
      return <Badge variant="destructive">{percent}%</Badge>;
    }
    return <Badge variant="secondary">{percent}%</Badge>;
  };

  const getFieldLabel = (field: string) => {
    const labels: Record<string, string> = {
      invoice_number: 'Rechnungsnummer',
      invoice_date: 'Rechnungsdatum',
      due_date: 'Fälligkeitsdatum',
      total_amount: 'Gesamtbetrag',
      net_amount: 'Nettobetrag',
      vat_amount: 'MwSt-Betrag',
      vat_rate: 'MwSt-Satz',
      vendor_name: 'Lieferantenname',
      vendor_address: 'Lieferantenadresse',
      iban: 'IBAN',
      bic: 'BIC',
      customer_number: 'Kundennummer',
    };
    return labels[field] || field;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Feld-spezifische Anpassungen</CardTitle>
      </CardHeader>
      <CardContent>
        {fieldData.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Noch keine feld-spezifischen Anpassungen vorhanden.
            <br />
            <span className="text-sm">
              Anpassungen werden nach User-Korrekturen automatisch gelernt.
            </span>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Backend</TableHead>
                <TableHead>Feld</TableHead>
                <TableHead className="text-right">Anpassung</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fieldData.map((row, index) => (
                <TableRow key={`${row.backend}-${row.field}-${index}`}>
                  <TableCell className="font-mono text-sm">{row.backend}</TableCell>
                  <TableCell>{getFieldLabel(row.field)}</TableCell>
                  <TableCell className="text-right">
                    {getAdjustmentBadge(row.adjustment)}
                  </TableCell>
                  <TableCell>{getAdjustmentIcon(row.adjustment)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {fieldData.length > 0 && (
          <p className="text-xs text-muted-foreground mt-4">
            Die Anpassungen basieren auf {stats.total_corrections || 0} User-Korrekturen.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
