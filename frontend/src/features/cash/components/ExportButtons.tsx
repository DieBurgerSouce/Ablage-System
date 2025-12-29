/**
 * Export Buttons
 *
 * Dropdown-Menu für CSV, PDF und DATEV Export.
 * Integriert sich nahtlos in die Kassenbuch-Toolbar.
 */

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/use-toast';
import { Download, FileSpreadsheet, FileText, FileDigit, Loader2 } from 'lucide-react';
import { cashService } from '@/lib/api/services/cash';

interface ExportButtonsProps {
  registerId: string;
  startDate?: string;
  endDate?: string;
  registerName?: string;
  disabled?: boolean;
}

type ExportFormat = 'csv' | 'pdf' | 'datev';

const EXPORT_FORMATS: { value: ExportFormat; label: string; icon: React.ReactNode; description: string }[] = [
  {
    value: 'csv',
    label: 'CSV (Excel)',
    icon: <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />,
    description: 'Semikolon-getrennt, UTF-8',
  },
  {
    value: 'pdf',
    label: 'PDF Bericht',
    icon: <FileText className="h-4 w-4" aria-hidden="true" />,
    description: 'Druckfertiger Bericht',
  },
  {
    value: 'datev',
    label: 'DATEV Export',
    icon: <FileDigit className="h-4 w-4" aria-hidden="true" />,
    description: 'Für Steuerberater',
  },
];

export function ExportButtons({
  registerId,
  startDate,
  endDate,
  registerName,
  disabled,
}: ExportButtonsProps) {
  const { toast } = useToast();
  const [isExporting, setIsExporting] = React.useState<ExportFormat | null>(null);

  const handleExport = async (format: ExportFormat) => {
    setIsExporting(format);

    try {
      let blob: Blob;
      let filename: string;
      const dateStr = new Date().toISOString().split('T')[0];
      const registerSlug = (registerName || 'kassenbuch').replace(/\s+/g, '-').toLowerCase();

      const params = {
        register_id: registerId,
        start_date: startDate,
        end_date: endDate,
      };

      switch (format) {
        case 'csv':
          blob = await cashService.exportCSV(params);
          filename = `${registerSlug}_${dateStr}.csv`;
          break;
        case 'pdf':
          blob = await cashService.exportPDF(params);
          filename = `${registerSlug}_${dateStr}.pdf`;
          break;
        case 'datev':
          blob = await cashService.exportDATEV(params);
          filename = `${registerSlug}_${dateStr}_DATEV.csv`;
          break;
      }

      // Download ausloesen
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast({
        title: 'Export erfolgreich',
        description: `${filename} wurde heruntergeladen`,
        variant: 'success',
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
      toast({
        title: 'Export fehlgeschlagen',
        description: errorMessage,
        variant: 'destructive',
      });
    } finally {
      setIsExporting(null);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={disabled || isExporting !== null}>
          {isExporting ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="mr-2 h-4 w-4" aria-hidden="true" />
          )}
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {EXPORT_FORMATS.map((format, index) => (
          <React.Fragment key={format.value}>
            {index > 0 && format.value === 'datev' && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={() => handleExport(format.value)}
              disabled={isExporting !== null}
              className="flex items-start gap-3 py-2"
            >
              <div className="mt-0.5">{format.icon}</div>
              <div className="flex flex-col">
                <span className="font-medium">{format.label}</span>
                <span className="text-xs text-muted-foreground">{format.description}</span>
              </div>
              {isExporting === format.value && (
                <Loader2 className="ml-auto h-4 w-4 animate-spin" aria-hidden="true" />
              )}
            </DropdownMenuItem>
          </React.Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default ExportButtons;
