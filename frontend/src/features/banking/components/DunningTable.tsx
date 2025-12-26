/**
 * DunningTable - Erweiterte Mahnungstabelle mit TanStack Table
 *
 * Features:
 * - Checkbox-Selektion pro Zeile fuer Bulk-Actions
 * - Sortierbare Spalten
 * - Filter (Status, Mahnstufe, B2B/B2C)
 * - Pagination
 * - BGB §286 Felder (B2B/B2C, Mahnstopp, Verzugszinsen)
 */

import { useState, useMemo } from 'react';
import {
    ColumnDef,
    ColumnFiltersState,
    SortingState,
    VisibilityState,
    flexRender,
    getCoreRowModel,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    useReactTable,
} from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
    DropdownMenu,
    DropdownMenuCheckboxItem,
    DropdownMenuContent,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    ArrowUpDown,
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
    Building2,
    User,
    PauseCircle,
    AlertTriangle,
    Phone,
    Mail,
    FileWarning,
    Gavel,
    Settings2,
} from 'lucide-react';
import type { DunningRecord } from '@/types/models/banking';
import { formatCurrency, formatDate } from '../utils/format';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface DunningTableProps {
    data: DunningRecord[];
    isLoading?: boolean;
    onRowClick?: (dunning: DunningRecord) => void;
    onSelectionChange?: (selectedIds: string[]) => void;
}

// ==================== Level/Status Configuration ====================

const DUNNING_LEVEL_CONFIG: Record<number, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; icon: React.ReactNode }> = {
    0: { label: 'Neu', variant: 'outline', icon: null },
    1: { label: 'Erinnerung', variant: 'secondary', icon: <Mail className="h-3 w-3" /> },
    2: { label: '1. Mahnung', variant: 'secondary', icon: <FileWarning className="h-3 w-3" /> },
    3: { label: '2. Mahnung', variant: 'default', icon: <Phone className="h-3 w-3" /> },
    4: { label: 'Letzte Mahnung', variant: 'destructive', icon: <AlertTriangle className="h-3 w-3" /> },
    5: { label: 'Inkasso', variant: 'destructive', icon: <Gavel className="h-3 w-3" /> },
};

const STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> = {
    'active': { label: 'Aktiv', variant: 'default' },
    'pending': { label: 'Ausstehend', variant: 'secondary' },
    'paid': { label: 'Bezahlt', variant: 'outline' },
    'closed': { label: 'Abgeschlossen', variant: 'outline' },
};

// ==================== Helper Components ====================

function DunningLevelBadge({ level }: { level: number }) {
    const config = DUNNING_LEVEL_CONFIG[level] ?? DUNNING_LEVEL_CONFIG[0];
    return (
        <Badge variant={config.variant} className="gap-1">
            {config.icon}
            {config.label}
        </Badge>
    );
}

function StatusBadge({ status }: { status: string }) {
    const config = STATUS_CONFIG[status] ?? STATUS_CONFIG['pending'];
    return <Badge variant={config.variant}>{config.label}</Badge>;
}

function B2BBadge({ isB2B }: { isB2B: boolean }) {
    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger>
                    <Badge variant={isB2B ? 'default' : 'secondary'} className="gap-1">
                        {isB2B ? <Building2 className="h-3 w-3" /> : <User className="h-3 w-3" />}
                        {isB2B ? 'B2B' : 'B2C'}
                    </Badge>
                </TooltipTrigger>
                <TooltipContent>
                    {isB2B
                        ? 'Geschaeftskunde: Basiszins + 9% = 11.27% p.a.'
                        : 'Privatkunde: Basiszins + 5% = 7.27% p.a.'
                    }
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

function MahnstoppIndicator({ mahnstopp, reason, until }: { mahnstopp: boolean; reason?: string | null; until?: string | null }) {
    if (!mahnstopp) return null;

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger>
                    <Badge variant="outline" className="gap-1 border-orange-500 text-orange-600">
                        <PauseCircle className="h-3 w-3" />
                        Mahnstopp
                    </Badge>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                    <div className="space-y-1">
                        <p className="font-medium">Mahnstopp aktiv</p>
                        {reason && <p className="text-sm">Grund: {reason}</p>}
                        {until && <p className="text-sm">Bis: {formatDate(until)}</p>}
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

// ==================== Column Definitions ====================

function getColumns(onRowClick?: (dunning: DunningRecord) => void): ColumnDef<DunningRecord>[] {
    return [
        {
            id: 'select',
            header: ({ table }) => (
                <Checkbox
                    checked={
                        table.getIsAllPageRowsSelected() ||
                        (table.getIsSomePageRowsSelected() && 'indeterminate')
                    }
                    onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
                    aria-label="Alle auswaehlen"
                />
            ),
            cell: ({ row }) => (
                <Checkbox
                    checked={row.getIsSelected()}
                    onCheckedChange={(value) => row.toggleSelected(!!value)}
                    aria-label="Zeile auswaehlen"
                    onClick={(e) => e.stopPropagation()}
                />
            ),
            enableSorting: false,
            enableHiding: false,
        },
        {
            accessorKey: 'invoice_number',
            header: ({ column }) => (
                <Button
                    variant="ghost"
                    onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                    className="-ml-4"
                >
                    Rechnung
                    <ArrowUpDown className="ml-2 h-4 w-4" />
                </Button>
            ),
            cell: ({ row }) => (
                <div className="font-medium">
                    {row.getValue('invoice_number') || '-'}
                </div>
            ),
        },
        {
            accessorKey: 'debtor_name',
            header: ({ column }) => (
                <Button
                    variant="ghost"
                    onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                    className="-ml-4"
                >
                    Debitor
                    <ArrowUpDown className="ml-2 h-4 w-4" />
                </Button>
            ),
            cell: ({ row }) => row.getValue('debtor_name') || '-',
        },
        {
            accessorKey: 'outstanding_amount',
            header: ({ column }) => (
                <Button
                    variant="ghost"
                    onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                    className="-ml-4"
                >
                    Betrag
                    <ArrowUpDown className="ml-2 h-4 w-4" />
                </Button>
            ),
            cell: ({ row }) => (
                <div className="text-right font-mono">
                    {formatCurrency(row.getValue('outstanding_amount') ?? 0)}
                </div>
            ),
        },
        {
            accessorKey: 'due_date',
            header: ({ column }) => (
                <Button
                    variant="ghost"
                    onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                    className="-ml-4"
                >
                    Faelligkeit
                    <ArrowUpDown className="ml-2 h-4 w-4" />
                </Button>
            ),
            cell: ({ row }) => {
                const dueDate = row.getValue('due_date') as string | null;
                if (!dueDate) return '-';

                const today = new Date();
                const due = new Date(dueDate);
                const daysOverdue = Math.floor((today.getTime() - due.getTime()) / (1000 * 60 * 60 * 24));

                return (
                    <div className="space-y-1">
                        <div>{formatDate(dueDate)}</div>
                        {daysOverdue > 0 && (
                            <div className="text-xs text-destructive font-medium">
                                +{daysOverdue} Tage
                            </div>
                        )}
                    </div>
                );
            },
        },
        {
            accessorKey: 'dunning_level',
            header: 'Mahnstufe',
            cell: ({ row }) => <DunningLevelBadge level={row.getValue('dunning_level') ?? 0} />,
            filterFn: (row, id, value) => {
                return value.includes(String(row.getValue(id)));
            },
        },
        {
            accessorKey: 'is_b2b',
            header: 'Typ',
            cell: ({ row }) => <B2BBadge isB2B={row.getValue('is_b2b') ?? true} />,
            filterFn: (row, id, value) => {
                const isB2B = row.getValue(id) as boolean;
                if (value === 'all') return true;
                return value === 'b2b' ? isB2B : !isB2B;
            },
        },
        {
            accessorKey: 'status',
            header: 'Status',
            cell: ({ row }) => {
                const dunning = row.original;
                return (
                    <div className="flex flex-col gap-1">
                        <StatusBadge status={dunning.status} />
                        <MahnstoppIndicator
                            mahnstopp={dunning.mahnstopp}
                            reason={dunning.mahnstopp_reason}
                            until={dunning.mahnstopp_until}
                        />
                    </div>
                );
            },
            filterFn: (row, id, value) => {
                if (value === 'all') return true;
                if (value === 'mahnstopp') return row.original.mahnstopp;
                return row.getValue(id) === value;
            },
        },
        {
            accessorKey: 'total_outstanding',
            header: ({ column }) => (
                <Button
                    variant="ghost"
                    onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
                    className="-ml-4"
                >
                    Gesamt
                    <ArrowUpDown className="ml-2 h-4 w-4" />
                </Button>
            ),
            cell: ({ row }) => {
                const dunning = row.original;
                const total = dunning.total_outstanding ?? dunning.outstanding_amount ?? 0;
                const fees = dunning.reminder_fee + dunning.accrued_interest;

                return (
                    <div className="text-right">
                        <div className="font-mono font-medium">{formatCurrency(total)}</div>
                        {fees > 0 && (
                            <div className="text-xs text-muted-foreground">
                                inkl. {formatCurrency(fees)} Gebuehren
                            </div>
                        )}
                        {dunning.b2b_pauschale_claimed && (
                            <div className="text-xs text-green-600">
                                +40€ Pauschale
                            </div>
                        )}
                    </div>
                );
            },
        },
        {
            id: 'actions',
            cell: ({ row }) => {
                const dunning = row.original;
                return (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                            e.stopPropagation();
                            onRowClick?.(dunning);
                        }}
                    >
                        Details
                    </Button>
                );
            },
        },
    ];
}

// ==================== Main Component ====================

export function DunningTable({
    data,
    isLoading = false,
    onRowClick,
    onSelectionChange,
}: DunningTableProps) {
    const [sorting, setSorting] = useState<SortingState>([]);
    const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
    const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
    const [rowSelection, setRowSelection] = useState({});

    const columns = useMemo(() => getColumns(onRowClick), [onRowClick]);

    const table = useReactTable({
        data,
        columns,
        onSortingChange: setSorting,
        onColumnFiltersChange: setColumnFilters,
        getCoreRowModel: getCoreRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        onColumnVisibilityChange: setColumnVisibility,
        onRowSelectionChange: (updater) => {
            const newSelection = typeof updater === 'function' ? updater(rowSelection) : updater;
            setRowSelection(newSelection);

            // Notify parent of selection changes
            if (onSelectionChange) {
                const selectedRows = Object.keys(newSelection).filter((key) => newSelection[key as keyof typeof newSelection]);
                const selectedIds = selectedRows.map((idx) => data[parseInt(idx)]?.id).filter(Boolean) as string[];
                onSelectionChange(selectedIds);
            }
        },
        state: {
            sorting,
            columnFilters,
            columnVisibility,
            rowSelection,
        },
        initialState: {
            pagination: {
                pageSize: 20,
            },
        },
    });

    const selectedCount = Object.keys(rowSelection).filter((key) => rowSelection[key as keyof typeof rowSelection]).length;

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className="flex flex-wrap items-center gap-4">
                <Input
                    placeholder="Rechnung suchen..."
                    value={(table.getColumn('invoice_number')?.getFilterValue() as string) ?? ''}
                    onChange={(event) =>
                        table.getColumn('invoice_number')?.setFilterValue(event.target.value)
                    }
                    className="max-w-xs"
                />

                <Select
                    value={(table.getColumn('status')?.getFilterValue() as string) ?? 'all'}
                    onValueChange={(value) =>
                        table.getColumn('status')?.setFilterValue(value === 'all' ? undefined : value)
                    }
                >
                    <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle Status</SelectItem>
                        <SelectItem value="active">Aktiv</SelectItem>
                        <SelectItem value="pending">Ausstehend</SelectItem>
                        <SelectItem value="mahnstopp">Mit Mahnstopp</SelectItem>
                        <SelectItem value="paid">Bezahlt</SelectItem>
                    </SelectContent>
                </Select>

                <Select
                    value={(table.getColumn('is_b2b')?.getFilterValue() as string) ?? 'all'}
                    onValueChange={(value) =>
                        table.getColumn('is_b2b')?.setFilterValue(value === 'all' ? undefined : value)
                    }
                >
                    <SelectTrigger className="w-[140px]">
                        <SelectValue placeholder="Kundentyp" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle</SelectItem>
                        <SelectItem value="b2b">B2B</SelectItem>
                        <SelectItem value="b2c">B2C</SelectItem>
                    </SelectContent>
                </Select>

                <div className="flex-1" />

                {selectedCount > 0 && (
                    <div className="text-sm text-muted-foreground">
                        {selectedCount} ausgewaehlt
                    </div>
                )}

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="outline" size="sm" className="ml-auto">
                            <Settings2 className="h-4 w-4 mr-2" />
                            Spalten
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        {table
                            .getAllColumns()
                            .filter((column) => column.getCanHide())
                            .map((column) => {
                                const columnLabels: Record<string, string> = {
                                    invoice_number: 'Rechnung',
                                    debtor_name: 'Debitor',
                                    outstanding_amount: 'Betrag',
                                    due_date: 'Faelligkeit',
                                    dunning_level: 'Mahnstufe',
                                    is_b2b: 'Kundentyp',
                                    status: 'Status',
                                    total_outstanding: 'Gesamt',
                                };
                                return (
                                    <DropdownMenuCheckboxItem
                                        key={column.id}
                                        className="capitalize"
                                        checked={column.getIsVisible()}
                                        onCheckedChange={(value) => column.toggleVisibility(!!value)}
                                    >
                                        {columnLabels[column.id] ?? column.id}
                                    </DropdownMenuCheckboxItem>
                                );
                            })}
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>

            {/* Table */}
            <div className="rounded-md border">
                <Table>
                    <TableHeader>
                        {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id}>
                                {headerGroup.headers.map((header) => (
                                    <TableHead key={header.id}>
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
                        {isLoading ? (
                            <TableRow>
                                <TableCell colSpan={columns.length} className="h-24 text-center">
                                    Laden...
                                </TableCell>
                            </TableRow>
                        ) : table.getRowModel().rows?.length ? (
                            table.getRowModel().rows.map((row) => (
                                <TableRow
                                    key={row.id}
                                    data-state={row.getIsSelected() && 'selected'}
                                    className={cn(
                                        'cursor-pointer',
                                        row.original.mahnstopp && 'bg-orange-50 dark:bg-orange-950/20'
                                    )}
                                    onClick={() => onRowClick?.(row.original)}
                                >
                                    {row.getVisibleCells().map((cell) => (
                                        <TableCell key={cell.id}>
                                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                        </TableCell>
                                    ))}
                                </TableRow>
                            ))
                        ) : (
                            <TableRow>
                                <TableCell colSpan={columns.length} className="h-24 text-center">
                                    Keine Mahnvorgaenge gefunden
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-2">
                <div className="text-sm text-muted-foreground">
                    Seite {table.getState().pagination.pageIndex + 1} von{' '}
                    {table.getPageCount()}
                    {' '}({data.length} Eintraege)
                </div>
                <div className="flex items-center space-x-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => table.setPageIndex(0)}
                        disabled={!table.getCanPreviousPage()}
                    >
                        <ChevronsLeft className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => table.previousPage()}
                        disabled={!table.getCanPreviousPage()}
                    >
                        <ChevronLeft className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => table.nextPage()}
                        disabled={!table.getCanNextPage()}
                    >
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => table.setPageIndex(table.getPageCount() - 1)}
                        disabled={!table.getCanNextPage()}
                    >
                        <ChevronsRight className="h-4 w-4" />
                    </Button>
                </div>
            </div>
        </div>
    );
}
