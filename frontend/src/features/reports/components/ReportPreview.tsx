/**
 * ReportPreview Component
 *
 * Zeigt eine Vorschau der Report-Daten als Tabelle oder Platzhalter für Chart-Typen.
 * Bietet Download-Buttons für verschiedene Formate.
 */

import {
  BarChart3,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  Table as TableIcon,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { usePreview, useExecuteReport } from '../hooks/useReports';
import type { ChartType, ExportFormat } from '../types';

interface ReportPreviewProps {
  templateId: string | undefined;
  chartType?: ChartType;
  limit?: number;
}

const chartTypeLabels: Record<ChartType, string> = {
  bar: 'Balkendiagramm',
  line: 'Liniendiagramm',
  pie: 'Kreisdiagramm',
  area: 'Flaechendiagramm',
  stacked_bar: 'Gestapeltes Balkendiagramm',
};

const downloadFormats: { format: ExportFormat; label: string; icon: typeof FileText }[] = [
  { format: 'csv', label: 'CSV', icon: FileText },
  { format: 'excel', label: 'Excel', icon: FileSpreadsheet },
  { format: 'pdf', label: 'PDF', icon: FileText },
];

export function ReportPreview({
  templateId,
  chartType,
  limit = 10,
}: ReportPreviewProps) {
  const { data: preview, isLoading } = usePreview(templateId, limit);
  const executeMutation = useExecuteReport();

  const handleDownload = (format: ExportFormat) => {
    if (!templateId) return;
    executeMutation.mutate({
      templateId,
      data: { format },
    });
  };

  if (!templateId) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center py-12">
          <TableIcon className="h-12 w-12 text-muted-foreground mb-4" />
          <p className="text-muted-foreground text-center">
            Erstellen Sie zuerst den Report, um eine Vorschau zu sehen.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Non-table chart types: show placeholder
  if (chartType && chartType !== 'bar') {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Vorschau</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <BarChart3 className="h-16 w-16 text-muted-foreground mb-4" />
          <p className="text-muted-foreground text-center">
            Vorschau für {chartTypeLabels[chartType] || chartType} wird nach dem Ausführen angezeigt
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Daten-Tabelle */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Datenvorschau</CardTitle>
          {preview && (
            <CardDescription>
              {preview.preview_limit} von {preview.total_available} Einträgen
            </CardDescription>
          )}
        </CardHeader>
        <CardContent>
          {preview && preview.data.length > 0 ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {preview.columns.map((col) => (
                      <TableHead key={col} className="whitespace-nowrap">
                        {col}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.data.map((row, idx) => (
                    <TableRow key={idx}>
                      {preview.columns.map((col) => (
                        <TableCell
                          key={col}
                          className="whitespace-nowrap max-w-[200px] truncate"
                        >
                          {String(row[col] ?? '-')}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center text-muted-foreground py-8">
              <TableIcon className="h-10 w-10 mx-auto mb-3 opacity-50" />
              <p>Keine Daten für die Vorschau verfügbar.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Download-Buttons */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Export</CardTitle>
          <CardDescription>
            Report in verschiedenen Formaten herunterladen.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {downloadFormats.map(({ format, label, icon: _Icon }) => (
              <Button
                key={format}
                variant="outline"
                size="sm"
                onClick={() => handleDownload(format)}
                disabled={executeMutation.isPending}
              >
                {executeMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Download className="h-4 w-4 mr-2" />
                )}
                {label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
