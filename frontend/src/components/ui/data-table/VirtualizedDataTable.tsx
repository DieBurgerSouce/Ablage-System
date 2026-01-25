/**
 * VirtualizedDataTable
 *
 * Erweiterung von EnterpriseDataTable mit Virtualisierung fuer grosse Datensaetze.
 * Verwendet TanStack Virtual fuer effizientes Rendering von 1000+ Zeilen.
 *
 * Features:
 * - Row Virtualization (nur sichtbare Zeilen werden gerendert)
 * - Sticky Header
 * - Intersection Observer fuer Lazy Loading
 * - Smooth Scrolling
 * - Keyboard Navigation
 *
 * Phase 4.2 der Feature-Roadmap (Januar 2026)
 */

"use client"

import * as React from "react"
import {
    type ColumnDef,
    type ColumnFiltersState,
    type SortingState,
    type VisibilityState,
    type RowSelectionState,
    type RowData,
    flexRender,
    getCoreRowModel,
    getFilteredRowModel,
    getSortedRowModel,
    useReactTable,
    type OnChangeFn,
} from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import {
    Download,
    FileSpreadsheet,
    FileText,
    Loader2,
    ChevronsUpDown,
    ChevronUp,
    ChevronDown,
} from "lucide-react"

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
    DropdownMenuCheckboxItem,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

// ==================== Types ====================

export interface VirtualizedDataTableProps<TData, TValue> {
    columns: ColumnDef<TData, TValue>[]
    data: TData[]

    // Virtualization config
    /** Row height in pixels (default: 48) */
    rowHeight?: number
    /** Overscan - how many rows to render outside the visible area (default: 10) */
    overscan?: number
    /** Maximum height of the table container (default: 600px) */
    maxHeight?: number | string

    // Search/Filter
    searchColumn?: string
    searchPlaceholder?: string
    globalFilter?: boolean

    // Features
    enableSorting?: boolean
    enableFiltering?: boolean
    enableColumnVisibility?: boolean
    enableRowSelection?: boolean
    enableExport?: boolean
    enableStickyHeader?: boolean

    // Loading states
    isLoading?: boolean
    /** Show loading skeleton for initial load */
    isInitialLoading?: boolean
    /** Callback when more data should be loaded (infinite scroll) */
    onLoadMore?: () => void
    /** Is more data being loaded? */
    isLoadingMore?: boolean
    /** Are there more items to load? */
    hasMore?: boolean

    // Controlled state
    sorting?: SortingState
    onSortingChange?: OnChangeFn<SortingState>
    rowSelection?: RowSelectionState
    onRowSelectionChange?: OnChangeFn<RowSelectionState>
    columnFilters?: ColumnFiltersState
    onColumnFiltersChange?: OnChangeFn<ColumnFiltersState>

    // Callbacks
    onRowClick?: (row: TData) => void

    // Styling
    className?: string
    compact?: boolean
}

// ==================== Helper Components ====================

function SortableHeader({
    column,
    children,
}: {
    column: {
        getCanSort: () => boolean
        getIsSorted: () => false | 'asc' | 'desc'
        toggleSorting: (desc?: boolean) => void
    }
    children: React.ReactNode
}) {
    const isSortable = column.getCanSort()
    const sortDirection = column.getIsSorted()

    if (!isSortable) {
        return <>{children}</>
    }

    return (
        <Button
            variant="ghost"
            size="sm"
            className="-ml-3 h-8 data-[state=open]:bg-accent"
            onClick={() => column.toggleSorting(sortDirection === 'asc')}
        >
            {children}
            {sortDirection === 'asc' ? (
                <ChevronUp className="ml-2 h-4 w-4" />
            ) : sortDirection === 'desc' ? (
                <ChevronDown className="ml-2 h-4 w-4" />
            ) : (
                <ChevronsUpDown className="ml-2 h-4 w-4 opacity-50" />
            )}
        </Button>
    )
}

function LoadingRows({
    columns,
    count = 5,
    rowHeight,
}: {
    columns: number
    count?: number
    rowHeight: number
}) {
    return (
        <>
            {Array.from({ length: count }).map((_, i) => (
                <TableRow key={`loading-${i}`} style={{ height: rowHeight }}>
                    {Array.from({ length: columns }).map((_, j) => (
                        <TableCell key={`loading-${i}-${j}`}>
                            <Skeleton className="h-4 w-full" />
                        </TableCell>
                    ))}
                </TableRow>
            ))}
        </>
    )
}

// ==================== Main Component ====================

export function VirtualizedDataTable<TData, TValue>({
    columns,
    data,
    rowHeight = 48,
    overscan = 10,
    maxHeight = 600,
    searchColumn,
    searchPlaceholder = "Suchen...",
    globalFilter = false,
    enableSorting = true,
    enableFiltering = true,
    enableColumnVisibility = true,
    enableRowSelection = false,
    enableExport = true,
    enableStickyHeader = true,
    isLoading = false,
    isInitialLoading = false,
    onLoadMore,
    isLoadingMore = false,
    hasMore = false,
    sorting: controlledSorting,
    onSortingChange: setControlledSorting,
    rowSelection: controlledRowSelection,
    onRowSelectionChange: setControlledRowSelection,
    columnFilters: controlledColumnFilters,
    onColumnFiltersChange: setControlledColumnFilters,
    onRowClick,
    className,
    compact = false,
}: VirtualizedDataTableProps<TData, TValue>) {
    // Refs
    const tableContainerRef = React.useRef<HTMLDivElement>(null)

    // Internal state
    const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({})
    const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
    const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
    const [sorting, setSorting] = React.useState<SortingState>([])
    const [globalFilterValue, setGlobalFilterValue] = React.useState("")

    // Table instance
    const table = useReactTable({
        data,
        columns,
        state: {
            sorting: controlledSorting ?? sorting,
            columnVisibility,
            rowSelection: controlledRowSelection ?? rowSelection,
            columnFilters: controlledColumnFilters ?? columnFilters,
            globalFilter: globalFilterValue,
        },
        enableRowSelection,
        onRowSelectionChange: setControlledRowSelection ?? setRowSelection,
        onSortingChange: setControlledSorting ?? setSorting,
        onColumnFiltersChange: setControlledColumnFilters ?? setColumnFilters,
        onColumnVisibilityChange: setColumnVisibility,
        onGlobalFilterChange: setGlobalFilterValue,
        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getSortedRowModel: enableSorting ? getSortedRowModel() : undefined,
    })

    // Get filtered rows for virtualization
    const { rows } = table.getRowModel()

    // Virtualizer for rows
    const rowVirtualizer = useVirtualizer({
        count: rows.length,
        getScrollElement: () => tableContainerRef.current,
        estimateSize: () => rowHeight,
        overscan,
    })

    const virtualRows = rowVirtualizer.getVirtualItems()
    const totalSize = rowVirtualizer.getTotalSize()

    // Intersection observer for infinite scroll
    const loadMoreRef = React.useRef<HTMLTableRowElement>(null)

    React.useEffect(() => {
        if (!onLoadMore || !hasMore || isLoadingMore) return

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0]?.isIntersecting) {
                    onLoadMore()
                }
            },
            {
                root: tableContainerRef.current,
                rootMargin: '100px',
                threshold: 0.1,
            }
        )

        if (loadMoreRef.current) {
            observer.observe(loadMoreRef.current)
        }

        return () => observer.disconnect()
    }, [onLoadMore, hasMore, isLoadingMore])

    // Keyboard navigation
    const [focusedRowIndex, setFocusedRowIndex] = React.useState<number | null>(null)

    const handleKeyDown = React.useCallback(
        (e: React.KeyboardEvent) => {
            if (!rows.length) return

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault()
                    setFocusedRowIndex((prev) =>
                        prev === null ? 0 : Math.min(prev + 1, rows.length - 1)
                    )
                    break
                case 'ArrowUp':
                    e.preventDefault()
                    setFocusedRowIndex((prev) =>
                        prev === null ? rows.length - 1 : Math.max(prev - 1, 0)
                    )
                    break
                case 'Enter':
                    if (focusedRowIndex !== null && onRowClick) {
                        e.preventDefault()
                        onRowClick(rows[focusedRowIndex].original)
                    }
                    break
                case 'Home':
                    e.preventDefault()
                    setFocusedRowIndex(0)
                    rowVirtualizer.scrollToIndex(0)
                    break
                case 'End':
                    e.preventDefault()
                    setFocusedRowIndex(rows.length - 1)
                    rowVirtualizer.scrollToIndex(rows.length - 1)
                    break
            }
        },
        [rows, focusedRowIndex, onRowClick, rowVirtualizer]
    )

    // Scroll focused row into view
    React.useEffect(() => {
        if (focusedRowIndex !== null) {
            rowVirtualizer.scrollToIndex(focusedRowIndex, { align: 'auto' })
        }
    }, [focusedRowIndex, rowVirtualizer])

    // Export handler
    const handleExport = (format: 'csv' | 'excel') => {
        if (format === 'csv') {
            const visibleColumns = table.getVisibleLeafColumns()
            const headers = visibleColumns.map((col) => col.id).join(',')
            const csvRows = rows
                .map((row) =>
                    visibleColumns
                        .map((col) => {
                            const value = row.getValue(col.id)
                            if (
                                typeof value === 'string' &&
                                (value.includes(',') || value.includes('"'))
                            ) {
                                return `"${value.replace(/"/g, '""')}"`
                            }
                            return String(value ?? '')
                        })
                        .join(',')
                )
                .join('\n')

            const csv = `${headers}\n${csvRows}`
            const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `export-${new Date().toISOString().split('T')[0]}.csv`
            a.click()
            URL.revokeObjectURL(url)
        }
    }

    const isFiltered = columnFilters.length > 0 || globalFilterValue !== ''

    // Padding for virtualization
    const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0
    const paddingBottom =
        virtualRows.length > 0
            ? totalSize - (virtualRows[virtualRows.length - 1]?.end ?? 0)
            : 0

    return (
        <div className={cn("space-y-4", className)}>
            {/* Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-1 items-center space-x-2">
                    {enableFiltering && (
                        <Input
                            placeholder={searchPlaceholder}
                            value={
                                globalFilter
                                    ? globalFilterValue
                                    : (table.getColumn(searchColumn ?? '')?.getFilterValue() as string) ??
                                        ""
                            }
                            onChange={(event) => {
                                if (globalFilter) {
                                    setGlobalFilterValue(event.target.value)
                                } else if (searchColumn) {
                                    table.getColumn(searchColumn)?.setFilterValue(event.target.value)
                                }
                            }}
                            className="h-8 w-[150px] lg:w-[250px]"
                        />
                    )}
                    {isFiltered && (
                        <Button
                            variant="ghost"
                            onClick={() => {
                                table.resetColumnFilters()
                                setGlobalFilterValue("")
                            }}
                            className="h-8 px-2 lg:px-3"
                        >
                            Zurücksetzen
                        </Button>
                    )}
                </div>

                <div className="flex items-center space-x-2">
                    {/* Row count */}
                    <span className="text-sm text-muted-foreground">
                        {rows.length.toLocaleString('de-DE')} Einträge
                    </span>

                    {/* Export Dropdown */}
                    {enableExport && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" size="sm" className="h-8">
                                    <Download className="mr-2 h-4 w-4" />
                                    Export
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => handleExport('csv')}>
                                    <FileText className="mr-2 h-4 w-4" />
                                    CSV
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleExport('excel')}>
                                    <FileSpreadsheet className="mr-2 h-4 w-4" />
                                    Excel
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}

                    {/* Column Visibility */}
                    {enableColumnVisibility && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" size="sm" className="h-8">
                                    Spalten
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-[150px]">
                                {table
                                    .getAllColumns()
                                    .filter((col) => col.getCanHide())
                                    .map((column) => (
                                        <DropdownMenuCheckboxItem
                                            key={column.id}
                                            checked={column.getIsVisible()}
                                            onCheckedChange={(value) =>
                                                column.toggleVisibility(!!value)
                                            }
                                        >
                                            {column.id}
                                        </DropdownMenuCheckboxItem>
                                    ))}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
                </div>
            </div>

            {/* Virtualized Table */}
            <div
                ref={tableContainerRef}
                className="rounded-md border overflow-auto"
                style={{
                    maxHeight: typeof maxHeight === 'number' ? `${maxHeight}px` : maxHeight,
                }}
                onKeyDown={handleKeyDown}
                tabIndex={0}
                role="grid"
                aria-rowcount={rows.length}
            >
                <Table style={{ width: '100%' }}>
                    {/* Sticky Header */}
                    <TableHeader
                        className={cn(
                            enableStickyHeader && "sticky top-0 z-10 bg-background shadow-sm"
                        )}
                    >
                        {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id}>
                                {headerGroup.headers.map((header) => (
                                    <TableHead
                                        key={header.id}
                                        colSpan={header.colSpan}
                                        className={cn(
                                            "whitespace-nowrap",
                                            header.column.columnDef.meta?.className
                                        )}
                                        style={{ width: header.getSize() }}
                                    >
                                        {header.isPlaceholder ? null : (
                                            <SortableHeader column={header.column}>
                                                {flexRender(
                                                    header.column.columnDef.header,
                                                    header.getContext()
                                                )}
                                            </SortableHeader>
                                        )}
                                    </TableHead>
                                ))}
                            </TableRow>
                        ))}
                    </TableHeader>

                    {/* Virtualized Body */}
                    <TableBody>
                        {isInitialLoading ? (
                            <LoadingRows
                                columns={columns.length}
                                count={10}
                                rowHeight={rowHeight}
                            />
                        ) : isLoading && rows.length === 0 ? (
                            <TableRow>
                                <TableCell
                                    colSpan={columns.length}
                                    className="h-24 text-center"
                                >
                                    <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                                    <span className="mt-2 block text-muted-foreground">
                                        Laden...
                                    </span>
                                </TableCell>
                            </TableRow>
                        ) : rows.length === 0 ? (
                            <TableRow>
                                <TableCell
                                    colSpan={columns.length}
                                    className="h-24 text-center"
                                >
                                    Keine Ergebnisse.
                                </TableCell>
                            </TableRow>
                        ) : (
                            <>
                                {/* Top padding for virtualization */}
                                {paddingTop > 0 && (
                                    <tr>
                                        <td
                                            style={{ height: paddingTop }}
                                            colSpan={columns.length}
                                        />
                                    </tr>
                                )}

                                {/* Virtual rows */}
                                {virtualRows.map((virtualRow) => {
                                    const row = rows[virtualRow.index]
                                    const isFocused = focusedRowIndex === virtualRow.index

                                    return (
                                        <TableRow
                                            key={row.id}
                                            data-index={virtualRow.index}
                                            data-state={row.getIsSelected() && "selected"}
                                            onClick={() => {
                                                setFocusedRowIndex(virtualRow.index)
                                                onRowClick?.(row.original)
                                            }}
                                            className={cn(
                                                onRowClick &&
                                                    "cursor-pointer hover:bg-muted/50",
                                                compact && "h-8",
                                                isFocused &&
                                                    "ring-2 ring-primary ring-inset"
                                            )}
                                            style={{ height: rowHeight }}
                                            role="row"
                                            aria-rowindex={virtualRow.index + 1}
                                            tabIndex={isFocused ? 0 : -1}
                                        >
                                            {row.getVisibleCells().map((cell) => (
                                                <TableCell
                                                    key={cell.id}
                                                    className={cn(
                                                        cell.column.columnDef.meta
                                                            ?.className,
                                                        compact && "py-1"
                                                    )}
                                                    style={{
                                                        width: cell.column.getSize(),
                                                    }}
                                                >
                                                    {flexRender(
                                                        cell.column.columnDef.cell,
                                                        cell.getContext()
                                                    )}
                                                </TableCell>
                                            ))}
                                        </TableRow>
                                    )
                                })}

                                {/* Bottom padding for virtualization */}
                                {paddingBottom > 0 && (
                                    <tr>
                                        <td
                                            style={{ height: paddingBottom }}
                                            colSpan={columns.length}
                                        />
                                    </tr>
                                )}

                                {/* Load more trigger */}
                                {hasMore && (
                                    <TableRow ref={loadMoreRef}>
                                        <TableCell
                                            colSpan={columns.length}
                                            className="h-12 text-center"
                                        >
                                            {isLoadingMore ? (
                                                <div className="flex items-center justify-center gap-2">
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                    <span className="text-sm text-muted-foreground">
                                                        Mehr laden...
                                                    </span>
                                                </div>
                                            ) : (
                                                <span className="text-sm text-muted-foreground">
                                                    Weiter scrollen für mehr Einträge
                                                </span>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                )}
                            </>
                        )}
                    </TableBody>
                </Table>
            </div>

            {/* Footer info */}
            <div className="flex items-center justify-between px-2 text-sm text-muted-foreground">
                <div>
                    {enableRowSelection && (
                        <>
                            {table.getFilteredSelectedRowModel().rows.length} von{" "}
                            {rows.length.toLocaleString('de-DE')} Zeile(n) ausgewählt
                        </>
                    )}
                </div>
                <div>
                    {rows.length.toLocaleString('de-DE')} Einträge insgesamt
                    {hasMore && " (mehr verfügbar)"}
                </div>
            </div>
        </div>
    )
}

export default VirtualizedDataTable
