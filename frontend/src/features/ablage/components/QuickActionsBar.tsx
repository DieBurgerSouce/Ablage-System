/**
 * QuickActionsBar - Primaere Aktionen (Upload + Export)
 *
 * Position: Unter Header, ueber Insights
 *
 * Zeigt NUR:
 * - Upload Button (oeffnet DocumentUploadDialog)
 * - Export Dropdown (CSV, PDF, ZIP)
 * - Mahnung erstellen (nur bei Rechnungen fuer Kunden)
 *
 * KEINE Bulk-Actions hier! Diese sind NUR in BulkActionsToolbar.
 */

import { useState, useCallback } from 'react';
import {
  Upload,
  Download,
  FileSpreadsheet,
  Mail,
  ChevronDown,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface QuickActionsBarProps {
  category: string;
  entityType: 'customer' | 'supplier';
  totalCount: number;
  isLoading?: boolean;
  onUploadClick: () => void;
  onExportCsv?: () => Promise<void>;
  onExportPdf?: () => Promise<void>;
  onDownloadZip?: () => Promise<void>;
  onCreateReminder?: () => Promise<void>;
}

// ==================== Helper ====================

const INVOICE_CATEGORIES = ['rechnungen', 'offene_rechnungen', 'mahnungen'];

// ==================== Sub-Components ====================

function ActionButton({
  icon: Icon,
  label,
  onClick,
  isLoading,
  disabled,
  variant = 'outline',
  className,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void | Promise<void>;
  isLoading?: boolean;
  disabled?: boolean;
  variant?: 'default' | 'outline' | 'ghost' | 'destructive';
  className?: string;
}) {
  const [loading, setLoading] = useState(false);

  const handleClick = useCallback(async () => {
    if (loading || isLoading || disabled) return;
    const result = onClick();
    if (result instanceof Promise) {
      setLoading(true);
      try {
        await result;
      } finally {
        setLoading(false);
      }
    }
  }, [onClick, loading, isLoading, disabled]);

  const showLoading = loading || isLoading;

  return (
    <Button
      variant={variant}
      size="sm"
      onClick={handleClick}
      disabled={showLoading || disabled}
      className={cn('gap-2', className)}
    >
      {showLoading ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <Icon className="w-4 h-4" />
      )}
      <span className="hidden sm:inline">{label}</span>
    </Button>
  );
}

function ExportDropdown({
  onExportCsv,
  onExportPdf,
  onDownloadZip,
  disabled,
}: {
  onExportCsv?: () => Promise<void>;
  onExportPdf?: () => Promise<void>;
  onDownloadZip?: () => Promise<void>;
  disabled?: boolean;
}) {
  const [isLoading, setIsLoading] = useState(false);

  const handleExport = useCallback(async (exportFn?: () => Promise<void>) => {
    if (!exportFn || isLoading) return;
    setIsLoading(true);
    try {
      await exportFn();
    } finally {
      setIsLoading(false);
    }
  }, [isLoading]);

  const hasExportOptions = onExportCsv || onExportPdf || onDownloadZip;

  if (!hasExportOptions) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled || isLoading} className="gap-2">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Download className="w-4 h-4" />
          )}
          <span className="hidden sm:inline">Export</span>
          <ChevronDown className="w-3 h-3 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {onExportCsv && (
          <DropdownMenuItem onClick={() => handleExport(onExportCsv)}>
            <FileSpreadsheet className="w-4 h-4 mr-2" />
            Als CSV exportieren
          </DropdownMenuItem>
        )}
        {onExportPdf && (
          <DropdownMenuItem onClick={() => handleExport(onExportPdf)}>
            <Download className="w-4 h-4 mr-2" />
            Als PDF exportieren
          </DropdownMenuItem>
        )}
        {onDownloadZip && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => handleExport(onDownloadZip)}>
              <Download className="w-4 h-4 mr-2" />
              Alle als ZIP herunterladen
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ==================== Main Component ====================

export function QuickActionsBar({
  category,
  entityType,
  totalCount,
  isLoading,
  onUploadClick,
  onExportCsv,
  onExportPdf,
  onDownloadZip,
  onCreateReminder,
}: QuickActionsBarProps) {
  const isInvoiceCategory = INVOICE_CATEGORIES.includes(category);
  const isCustomer = entityType === 'customer';

  return (
    <div data-testid="quick-actions-bar" className="flex flex-wrap items-center gap-3 p-3 bg-muted/30 rounded-lg border">
      {/* Primary Actions */}
      <div className="flex items-center gap-2">
        <ActionButton
          icon={Upload}
          label="Dokument hochladen"
          onClick={onUploadClick}
          variant="default"
        />

        <ExportDropdown
          onExportCsv={onExportCsv}
          onExportPdf={onExportPdf}
          onDownloadZip={onDownloadZip}
          disabled={totalCount === 0 || isLoading}
        />

        {/* Category-specific primary actions */}
        {isInvoiceCategory && isCustomer && onCreateReminder && (
          <ActionButton
            icon={Mail}
            label="Mahnung erstellen"
            onClick={onCreateReminder}
            disabled={totalCount === 0 || isLoading}
          />
        )}
      </div>

      {/* Total count indicator */}
      {totalCount > 0 && (
        <span className="text-xs text-muted-foreground ml-auto">
          {totalCount} Dokument{totalCount !== 1 ? 'e' : ''} gesamt
        </span>
      )}
    </div>
  );
}

export default QuickActionsBar;
