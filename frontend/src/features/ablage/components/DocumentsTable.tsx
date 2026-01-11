/**
 * DocumentsTable - Wiederverwendbare Dokumenten-Tabelle
 * Refactored to use Generic DataGrid
 */

import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  createColumnHelper,
  type SortingState,
  type RowSelectionState,
  type OnChangeFn,
} from '@tanstack/react-table';
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FolderOpen,
  FileText,
  Upload,
  Eye,
  Download,
  MoreHorizontal,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  PROCESSING_STATUS_CONFIG,
  PAYMENT_STATUS_CONFIG,
  type CategoryDocumentResponse,
} from '../types';
import { DataGrid } from '@/components/ui/data-grid/DataGrid';

// ==================== Types ====================

interface DocumentsTableProps {
  documents: CategoryDocumentResponse[];
  showPaymentStatus?: boolean;
  isLoading?: boolean;
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  rowSelection: RowSelectionState;
  onRowSelectionChange: OnChangeFn<RowSelectionState>;
  onDocumentClick?: (document: CategoryDocumentResponse) => void;
  onDownloadClick?: (document: CategoryDocumentResponse) => void;
}

interface DocumentsEmptyStateProps {
  hasFilters?: boolean;
  onUploadClick?: () => void;
  categoryLabel?: string;
}

// ==================== Format Helpers ====================

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const formatAmount = (amount: number | null, currency = 'EUR') => {
  if (amount === null) return '-';
  return amount.toLocaleString('de-DE', {
    style: 'currency',
    currency,
  });
};

// ==================== Column Helper ====================

const columnHelper = createColumnHelper<CategoryDocumentResponse>();

// ==================== Loading Skeleton ====================

export function DocumentsTableSkeleton({
  showPaymentStatus = false,
}: {
  showPaymentStatus?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10"></TableHead>
              <TableHead>Dateiname</TableHead>
              <TableHead>Dokumentnummer</TableHead>
              <TableHead>Datum</TableHead>
              <TableHead>Betrag</TableHead>
              <TableHead>Status</TableHead>
              {showPaymentStatus && <TableHead>Zahlung</TableHead>}
              {showPaymentStatus && <TableHead>Fällig</TableHead>}
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[1, 2, 3, 4, 5].map((i) => (
              <TableRow key={i}>
                <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                <TableCell><Skeleton className="h-4 w-[200px]" /></TableCell>
                <TableCell><Skeleton className="h-4 w-[100px]" /></TableCell>
                <TableCell><Skeleton className="h-4 w-[80px]" /></TableCell>
                <TableCell><Skeleton className="h-4 w-[80px]" /></TableCell>
                <TableCell><Skeleton className="h-6 w-[80px]" /></TableCell>
                {showPaymentStatus && <TableCell><Skeleton className="h-6 w-[80px]" /></TableCell>}
                {showPaymentStatus && <TableCell><Skeleton className="h-4 w-[80px]" /></TableCell>}
                <TableCell><Skeleton className="h-8 w-8" /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ==================== Empty State ====================

export function DocumentsEmptyState({
  hasFilters = false,
  onUploadClick,
  categoryLabel,
}: DocumentsEmptyStateProps) {
  const title = categoryLabel
    ? `Keine ${categoryLabel}`
    : 'Keine Dokumente';

  return (
    <div
      className="flex flex-col items-center justify-center py-20 px-8 text-center"
      role="status"
      aria-label={title}
    >
      {/* Large Folder Icon */}
      <div className="w-24 h-24 rounded-2xl bg-muted/50 flex items-center justify-center mb-6">
        <FolderOpen className="w-12 h-12 text-muted-foreground/50" aria-hidden="true" />
      </div>

      {/* Title */}
      <h3 className="text-xl font-semibold text-foreground mb-2">
        {title}
      </h3>

      {/* Description */}
      <p className="text-muted-foreground max-w-sm mb-8">
        {hasFilters
          ? 'Mit den aktuellen Filtern wurden keine Dokumente gefunden. Passen Sie die Filterkriterien an.'
          : 'In dieser Kategorie befinden sich noch keine Dokumente.'}
      </p>

      {/* Large Upload CTA - Only when no filters and upload handler provided */}
      {!hasFilters && onUploadClick && (
        <Button
          size="lg"
          onClick={onUploadClick}
          className="gap-2 px-8 py-6 text-base font-medium shadow-lg hover:shadow-xl transition-shadow"
        >
          <Upload className="w-5 h-5" aria-hidden="true" />
          Dokument hochladen
        </Button>
      )}
    </div>
  );
}

// ==================== Main Component ====================

export function DocumentsTable({
  documents,
  showPaymentStatus = false,
  isLoading = false,
  sorting,
  onSortingChange,
  rowSelection,
  onRowSelectionChange,
  onDocumentClick,
  onDownloadClick,
}: DocumentsTableProps) {

  const columns = useMemo(() => {
    // Select column
    const selectColumn = columnHelper.display({
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Alle Dokumente auf dieser Seite auswählen"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label={`Dokument ${row.original.filename} auswählen`}
        />
      ),
      enableSorting: false,
      size: 40,
    });

    // Filename column
    const filenameColumn = columnHelper.accessor('filename', {
      header: 'Dateiname',
      cell: (info) => (
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true" />
          <Link
            to="/documents/$documentId"
            params={{ documentId: info.row.original.id }}
            className="font-medium hover:underline hover:text-primary transition-colors truncate max-w-[250px]"
            title={info.getValue()}
            onClick={(e) => {
              if (onDocumentClick) {
                e.preventDefault();
                onDocumentClick(info.row.original);
              }
            }}
          >
            {info.getValue()}
          </Link>
        </div>
      ),
    });

    // Document number column
    const documentNumberColumn = columnHelper.accessor('documentNumber', {
      header: 'Dokumentnummer',
      cell: (info) => (
        <span className="text-muted-foreground font-mono text-sm">
          {info.getValue() || '-'}
        </span>
      ),
      meta: {
        className: 'hidden md:table-cell',
      },
    });

    // Date column with sorting
    const documentDateColumn = columnHelper.accessor('documentDate', {
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
        >
          Datum
          {column.getIsSorted() === 'asc' ? (
            <ArrowUp className="ml-2 h-4 w-4" />
          ) : column.getIsSorted() === 'desc' ? (
            <ArrowDown className="ml-2 h-4 w-4" />
          ) : (
            <ArrowUpDown className="ml-2 h-4 w-4" />
          )}
        </Button>
      ),
      cell: (info) => formatDate(info.getValue()),
      sortingFn: 'datetime',
      meta: {
        className: 'hidden sm:table-cell',
      },
    });

    // Amount column with sorting
    const amountColumn = columnHelper.accessor('totalAmount', {
      header: ({ column }) => (
        <div className="text-right">
          <Button
            variant="ghost"
            size="sm"
            className="-mr-3 h-8"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Betrag
            {column.getIsSorted() === 'asc' ? (
              <ArrowUp className="ml-2 h-4 w-4" />
            ) : column.getIsSorted() === 'desc' ? (
              <ArrowDown className="ml-2 h-4 w-4" />
            ) : (
              <ArrowUpDown className="ml-2 h-4 w-4" />
            )}
          </Button>
        </div>
      ),
      cell: (info) => (
        <span className="text-right font-mono block">
          {formatAmount(info.getValue(), info.row.original.currency)}
        </span>
      ),
    });

    // Processing status column
    const processingStatusColumn = columnHelper.accessor('processingStatus', {
      header: 'Status',
      cell: (info) => {
        const status = info.getValue();
        const config = PROCESSING_STATUS_CONFIG[status];
        return (
          <Badge variant={config.variant}>
            {config.label}
          </Badge>
        );
      },
    });

    // Payment status column (conditional)
    const paymentStatusColumn = columnHelper.accessor('paymentStatus', {
      header: 'Zahlung',
      cell: (info) => {
        const status = info.getValue();
        if (!status) return '-';
        const config = PAYMENT_STATUS_CONFIG[status];
        return (
          <Badge className={config.className}>
            {config.label}
          </Badge>
        );
      },
    });

    // Due date column (conditional)
    const dueDateColumn = columnHelper.accessor('dueDate', {
      header: 'Fällig',
      cell: (info) => {
        const dueDate = info.getValue();
        if (!dueDate) return '-';
        const date = new Date(dueDate);
        const isOverdue = date < new Date();
        return (
          <span className={isOverdue ? 'text-destructive font-medium' : ''}>
            {formatDate(dueDate)}
          </span>
        );
      },
    });

    // Actions column
    const actionsColumn = columnHelper.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="text-right">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 opacity-0 group-hover:opacity-100 focus:opacity-100 focus-within:opacity-100 transition-opacity"
                aria-label={`Aktionen für ${row.original.filename}`}
                tabIndex={0}
              >
                <MoreHorizontal className="w-4 h-4" aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: row.original.id }}
                  className="flex items-center gap-2"
                >
                  <Eye className="w-4 h-4" aria-hidden="true" />
                  Anzeigen
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem
                className="gap-2"
                onClick={() => onDownloadClick?.(row.original)}
              >
                <Download className="w-4 h-4" aria-hidden="true" />
                Herunterladen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
      size: 50,
    });

    // Build final columns array based on showPaymentStatus
    if (showPaymentStatus) {
      return [
        selectColumn,
        filenameColumn,
        documentNumberColumn,
        documentDateColumn,
        amountColumn,
        processingStatusColumn,
        paymentStatusColumn,
        dueDateColumn,
        actionsColumn,
      ];
    }

    return [
      selectColumn,
      filenameColumn,
      documentNumberColumn,
      documentDateColumn,
      amountColumn,
      processingStatusColumn,
      actionsColumn,
    ];
  }, [showPaymentStatus, onDocumentClick, onDownloadClick]);

  if (isLoading) {
    return <DocumentsTableSkeleton showPaymentStatus={showPaymentStatus} />;
  }

  return (
    <div data-testid="documents-table">
      <DataGrid
        columns={columns}
        data={documents}
        sorting={sorting}
        onSortingChange={onSortingChange}
        rowSelection={rowSelection}
        onRowSelectionChange={onRowSelectionChange}
        searchColumn="filename"
        searchPlaceholder="Dokumente durchsuchen..."
      />
    </div>
  );
}

// ==================== Pagination Component ====================

interface DocumentsPaginationProps {
  currentPage: number;
  totalPages: number;
  totalCount: number;
  onPageChange: (page: number) => void;
}

export function DocumentsPagination({
  currentPage,
  totalPages,
  totalCount,
  onPageChange,
}: DocumentsPaginationProps) {
  return (
    <div className="flex items-center justify-between px-2 py-4">
      <div className="text-sm text-muted-foreground">
        Seite {currentPage} von {totalPages} ({totalCount} Dokumente)
      </div>
      <div className="flex items-center space-x-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
        >
          Zurück
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
        >
          Weiter
        </Button>
      </div>
    </div>
  );
}
