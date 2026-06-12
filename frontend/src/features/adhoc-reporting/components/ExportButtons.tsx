/**
 * ExportButtons Component
 * German Enterprise Document Platform
 */

import { Button } from '@/components/ui/button';
import { FileText, FileSpreadsheet, Table } from 'lucide-react';
import type { ExportFormat } from '../types/adhoc-reporting-types';
import { EXPORT_FORMAT_LABELS } from '../types/adhoc-reporting-types';

interface ExportButtonsProps {
  reportId: number;
  onExport: (format: ExportFormat) => void;
  isExporting?: boolean;
  disabled?: boolean;
}

const EXPORT_ICONS: Record<ExportFormat, React.ComponentType<{ className?: string }>> = {
  pdf: FileText,
  excel: FileSpreadsheet,
  csv: Table,
};

export function ExportButtons({
  reportId,
  onExport,
  isExporting = false,
  disabled = false,
}: ExportButtonsProps) {
  const formats: ExportFormat[] = ['pdf', 'excel', 'csv'];

  return (
    <div className="flex items-center space-x-2">
      <span className="text-sm text-muted-foreground mr-2">Exportieren:</span>
      {formats.map((format) => {
        const Icon = EXPORT_ICONS[format];
        return (
          <Button
            key={format}
            variant="outline"
            size="sm"
            onClick={() => onExport(format)}
            disabled={disabled || isExporting}
          >
            <Icon className="h-4 w-4 mr-2" />
            {EXPORT_FORMAT_LABELS[format]}
          </Button>
        );
      })}
    </div>
  );
}
