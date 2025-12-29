/**
 * DocumentsTable - Wiederverwendbare Dokumenten-Tabelle
 *
 * Props-basierte Komponente ohne direkten Router-Zugriff.
 * Features:
 * - Row-Selection mit Checkboxen
 * - Sortierbare Spalten
 * - Bedingte Zahlungsstatus-Spalten
 * - Loading/Empty States
 * - Pagination
 */

import { useMemo } from 'react';
import { Link } from '@tanstack/react-router';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
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
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
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

interface DocumentsPaginationProps {
  currentPage: number;
  totalPages: number;
  totalCount: number;
  onPageChange: (page: number) => void;
}

interface DocumentsEmptyStateProps {
  hasFilters?: boolean;
  onUploadClick?: () => void;
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
}: DocumentsEmptyStateProps) {
  return (
    <div
      className="text-center py-16 text-muted-foreground"
      role="status"
      aria-label="Keine Dokumente gefunden"
    >
      <FolderOpen className="w-16 h-16 mx-auto mb-4 opacity-30" aria-hidden="true" />
      <p className="text-lg font-medium">Keine Dokumente gefunden</p>
      <p className="text-sm mt-2">
        {hasFilters
          ? 'Passen Sie die Filterkriterien an'
          : 'Laden Sie Dokumente in diese Kategorie hoch'}
      </p>
      {!hasFilters && onUploadClick && (
        <Button className="mt-4 gap-2" onClick={onUploadClick}>
          <Upload className="w-4 h-4" aria-hidden="true" />
          Erstes Dokument hochladen
        </Button>
      )}
    </div>
  );
}

// ==================== Pagination ====================

export function DocumentsPagination({
  currentPage,
  totalPages,
  totalCount,
  onPageChange,
}: DocumentsPaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <nav
      className="flex items-center justify-between"
      aria-label="Seitennavigation"
      role="navigation"
    >
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Seite {currentPage + 1} von {totalPages} ({totalCount} Dokumente)
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 0}
          aria-label="Vorherige Seite"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Zurück
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages - 1}
          aria-label="Nächste Seite"
        >
          Weiter
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </nav>
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
  // ==================== Table Columns ====================

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
    });

    // Date column with sorting
    const documentDateColumn = columnHelper.accessor('documentDate', {
      header: ({ column }) => (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8"
          onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          aria-label={`Nach Datum sortieren (${
            column.getIsSorted() === 'asc'
              ? 'aufsteigend'
              : column.getIsSorted() === 'desc'
                ? 'absteigend'
                : 'keine Sortierung'
          })`}
        >
          Datum
          {column.getIsSorted() === 'asc' ? (
            <ArrowUp className="ml-2 h-4 w-4" aria-hidden="true" />
          ) : column.getIsSorted() === 'desc' ? (
            <ArrowDown className="ml-2 h-4 w-4" aria-hidden="true" />
          ) : (
            <ArrowUpDown className="ml-2 h-4 w-4" aria-hidden="true" />
          )}
        </Button>
      ),
      cell: (info) => formatDate(info.getValue()),
      sortingFn: 'datetime',
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
            aria-label={`Nach Betrag sortieren`}
          >
            Betrag
            {column.getIsSorted() === 'asc' ? (
              <ArrowUp className="ml-2 h-4 w-4" aria-hidden="true" />
            ) : column.getIsSorted() === 'desc' ? (
              <ArrowDown className="ml-2 h-4 w-4" aria-hidden="true" />
            ) : (
              <ArrowUpDown className="ml-2 h-4 w-4" aria-hidden="true" />
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
                className="h-8 w-8 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity"
                aria-label={`Aktionen für ${row.original.filename}`}
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

  // ==================== Table Instance ====================

  const table = useReactTable({
    data: documents,
    columns,
    state: {
      sorting,
      rowSelection,
    },
    onSortingChange,
    onRowSelectionChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (row) => row.id,
    enableRowSelection: true,
  });

  // ==================== Loading State ====================

  if (isLoading) {
    return <DocumentsTableSkeleton showPaymentStatus={showPaymentStatus} />;
  }

  // ==================== Render ====================

  return (
    <Card>
      <CardContent className="p-0">
        <Table role="grid" aria-label="Dokumentenliste">
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    style={{ width: header.getSize() }}
                    scope="col"
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                data-state={row.getIsSelected() && 'selected'}
                className="group"
                aria-selected={row.getIsSelected()}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
