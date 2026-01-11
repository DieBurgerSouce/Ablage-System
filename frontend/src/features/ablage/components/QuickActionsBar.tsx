/**
 * QuickActionsBar - Primaere und kontextbezogene Aktionen
 *
 * Position: Unter Header, ueber Insights
 *
 * Zeigt:
 * - Primaere Aktionen (immer sichtbar): Upload, Export, Mahnung erstellen
 * - Sekundaere Aktionen (bei Auswahl): Verschieben, Tags, Als bezahlt, Loeschen
 *
 * Die sekundaeren Aktionen erscheinen nur wenn selectedIds.length > 0
 */

import { useState, useCallback } from 'react';
import {
  Upload,
  Download,
  FileSpreadsheet,
  Mail,
  FolderInput,
  Tags,
  CheckCircle2,
  Trash2,
  ChevronDown,
  Loader2,
  X,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface QuickActionsBarProps {
  category: string;
  entityType: 'customer' | 'supplier';
  selectedIds: string[];
  totalCount: number;
  isLoading?: boolean;
  onUploadClick: () => void;
  onExportCsv?: () => Promise<void>;
  onExportPdf?: () => Promise<void>;
  onDownloadZip?: () => Promise<void>;
  onCreateReminder?: () => Promise<void>;
  onMoveCategory?: () => void;
  onSetTags?: () => void;
  onMarkAsPaid?: () => Promise<void>;
  onDelete?: () => Promise<void>;
  onClearSelection: () => void;
}

// ==================== Helper ====================

const INVOICE_CATEGORIES = ['rechnungen', 'offene_rechnungen', 'mahnungen'];
const OFFER_CATEGORIES = ['angebote', 'offene_angebote'];

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

function SelectionInfo({
  count,
  onClear,
}: {
  count: number;
  onClear: () => void;
}) {
  if (count === 0) return null;

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
      <Badge variant="secondary" className="bg-blue-100 dark:bg-blue-800">
        {count} ausgewaehlt
      </Badge>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={onClear}
      >
        <X className="w-3 h-3" />
      </Button>
    </div>
  );
}

// ==================== Main Component ====================

export function QuickActionsBar({
  category,
  entityType,
  selectedIds,
  totalCount,
  isLoading,
  onUploadClick,
  onExportCsv,
  onExportPdf,
  onDownloadZip,
  onCreateReminder,
  onMoveCategory,
  onSetTags,
  onMarkAsPaid,
  onDelete,
  onClearSelection,
}: QuickActionsBarProps) {
  const hasSelection = selectedIds.length > 0;
  const isInvoiceCategory = INVOICE_CATEGORIES.includes(category);
  const isOfferCategory = OFFER_CATEGORIES.includes(category);
  const isCustomer = entityType === 'customer';

  return (
    <div data-testid="quick-actions-bar" className="flex flex-wrap items-center gap-3 p-3 bg-muted/30 rounded-lg border">
      {/* Primary Actions - Always visible */}
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
          disabled={totalCount === 0}
        />

        {/* Category-specific primary actions */}
        {isInvoiceCategory && isCustomer && onCreateReminder && (
          <ActionButton
            icon={Mail}
            label="Mahnung erstellen"
            onClick={onCreateReminder}
            disabled={totalCount === 0}
          />
        )}
      </div>

      {/* Selection indicator and secondary actions */}
      {hasSelection && (
        <>
          <Separator orientation="vertical" className="h-8" />

          <SelectionInfo count={selectedIds.length} onClear={onClearSelection} />

          {/* Secondary Actions - Only with selection */}
          <div className="flex items-center gap-2">
            {onMoveCategory && (
              <ActionButton
                icon={FolderInput}
                label="Verschieben"
                onClick={onMoveCategory}
              />
            )}

            {onSetTags && (
              <ActionButton
                icon={Tags}
                label="Tags setzen"
                onClick={onSetTags}
              />
            )}

            {/* Invoice-specific bulk actions */}
            {isInvoiceCategory && onMarkAsPaid && (
              <ActionButton
                icon={CheckCircle2}
                label="Als bezahlt"
                onClick={onMarkAsPaid}
                className="text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-900/30"
              />
            )}

            {/* More actions dropdown for less common actions */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-1">
                  <MoreHorizontal className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {isOfferCategory && (
                  <DropdownMenuItem>
                    <CheckCircle2 className="w-4 h-4 mr-2" />
                    In Auftrag umwandeln
                  </DropdownMenuItem>
                )}
                {isOfferCategory && (
                  <DropdownMenuItem>
                    <Mail className="w-4 h-4 mr-2" />
                    Angebot erneuern
                  </DropdownMenuItem>
                )}
                {onDelete && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={onDelete}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="w-4 h-4 mr-2" />
                      Loeschen ({selectedIds.length})
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </>
      )}

      {/* Total count indicator */}
      {!hasSelection && totalCount > 0 && (
        <span className="text-xs text-muted-foreground ml-auto">
          {totalCount} Dokument{totalCount !== 1 ? 'e' : ''} gesamt
        </span>
      )}
    </div>
  );
}

export default QuickActionsBar;
