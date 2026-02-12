"use client"

import * as React from "react"
import {
    type ColumnDef,
    type ColumnFiltersState,
    type SortingState,
    type VisibilityState,
    type GroupingState,
    type ExpandedState,
    flexRender,
    getCoreRowModel,
    getFacetedRowModel,
    getFacetedUniqueValues,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    getGroupedRowModel,
    getExpandedRowModel,
    useReactTable,
    type OnChangeFn,
    type RowSelectionState,
    type RowData,
    type Row,
    type ColumnSizingState,
} from "@tanstack/react-table"
import {
    ChevronDown,
    ChevronRight,
    Download,
    FileSpreadsheet,
    FileText,
    GripVertical,
    Loader2,
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
    DropdownMenuSeparator,
    DropdownMenuCheckboxItem,
    DropdownMenuLabel,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

// Extend column meta for inline editing
declare module '@tanstack/table-core' {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    interface ColumnMeta<TData extends RowData, TValue> {
        className?: string
        editable?: boolean
        editComponent?: React.ComponentType<{
            value: TValue
            onChange: (value: TValue) => void
            onCancel: () => void
            onSave: () => void
        }>
        groupable?: boolean
    }
}

// Export types
export interface ExportConfig {
    filename?: string
    columns?: string[] // Column IDs to export
    includeHeaders?: boolean
}

export interface EnterpriseDataTableProps<TData, TValue> {
    columns: ColumnDef<TData, TValue>[]
    data: TData[]

    // Search/Filter
    searchColumn?: string
    searchPlaceholder?: string
    globalFilter?: boolean

    // Features
    enableSorting?: boolean
    enableFiltering?: boolean
    enableColumnVisibility?: boolean
    enableRowSelection?: boolean
    enableGrouping?: boolean
    enableColumnResizing?: boolean
    enableExport?: boolean
    enableInlineEdit?: boolean

    // Loading state
    isLoading?: boolean

    // Controlled state
    sorting?: SortingState
    onSortingChange?: OnChangeFn<SortingState>
    rowSelection?: RowSelectionState
    onRowSelectionChange?: OnChangeFn<RowSelectionState>
    columnFilters?: ColumnFiltersState
    onColumnFiltersChange?: OnChangeFn<ColumnFiltersState>
    grouping?: GroupingState
    onGroupingChange?: OnChangeFn<GroupingState>

    // Callbacks
    onRowClick?: (row: TData) => void
    onInlineEdit?: (row: TData, columnId: string, value: unknown) => Promise<void>
    onExport?: (format: 'csv' | 'excel' | 'pdf', config: ExportConfig) => void

    // Pagination
    pageSize?: number
    pageSizeOptions?: number[]

    // Styling
    className?: string
    compact?: boolean
}

// Default inline edit cell
function EditableCell<TValue>({
    value,
    onChange,
    onCancel,
    onSave,
}: {
    value: TValue
    onChange: (value: TValue) => void
    onCancel: () => void
    onSave: () => void
}) {
    const inputRef = React.useRef<HTMLInputElement>(null)

    React.useEffect(() => {
        inputRef.current?.focus()
        inputRef.current?.select()
    }, [])

    return (
        <Input
            ref={inputRef}
            value={String(value ?? '')}
            onChange={(e) => onChange(e.target.value as TValue)}
            onKeyDown={(e) => {
                if (e.key === 'Enter') onSave()
                if (e.key === 'Escape') onCancel()
            }}
            onBlur={onSave}
            className="h-7 w-full"
        />
    )
}

export function EnterpriseDataTable<TData, TValue>({
    columns,
    data,
    searchColumn,
    searchPlaceholder = "Suchen...",
    globalFilter = false,
    enableSorting = true,
    enableFiltering = true,
    enableColumnVisibility = true,
    enableRowSelection = false,
    enableGrouping = false,
    enableColumnResizing = false,
    enableExport = true,
    enableInlineEdit = false,
    isLoading = false,
    sorting: controlledSorting,
    onSortingChange: setControlledSorting,
    rowSelection: controlledRowSelection,
    onRowSelectionChange: setControlledRowSelection,
    columnFilters: controlledColumnFilters,
    onColumnFiltersChange: setControlledColumnFilters,
    grouping: controlledGrouping,
    onGroupingChange: setControlledGrouping,
    onRowClick,
    onInlineEdit,
    onExport,
    pageSize = 10,
    pageSizeOptions = [10, 20, 50, 100],
    className,
    compact = false,
}: EnterpriseDataTableProps<TData, TValue>) {
    // Internal state
    const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({})
    const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
    const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
    const [sorting, setSorting] = React.useState<SortingState>([])
    const [grouping, setGrouping] = React.useState<GroupingState>([])
    const [expanded, setExpanded] = React.useState<ExpandedState>({})
    const [columnSizing, setColumnSizing] = React.useState<ColumnSizingState>({})
    const [globalFilterValue, setGlobalFilterValue] = React.useState("")

    // Editing state
    const [editingCell, setEditingCell] = React.useState<{
        rowId: string
        columnId: string
        value: unknown
    } | null>(null)

    const table = useReactTable({
        data,
        columns,
        state: {
            sorting: controlledSorting ?? sorting,
            columnVisibility,
            rowSelection: controlledRowSelection ?? rowSelection,
            columnFilters: controlledColumnFilters ?? columnFilters,
            grouping: controlledGrouping ?? grouping,
            expanded,
            columnSizing,
            globalFilter: globalFilterValue,
        },
        enableRowSelection,
        enableGrouping,
        enableColumnResizing,
        columnResizeMode: 'onChange',
        onRowSelectionChange: setControlledRowSelection ?? setRowSelection,
        onSortingChange: setControlledSorting ?? setSorting,
        onColumnFiltersChange: setControlledColumnFilters ?? setColumnFilters,
        onColumnVisibilityChange: setColumnVisibility,
        onGroupingChange: setControlledGrouping ?? setGrouping,
        onExpandedChange: setExpanded,
        onColumnSizingChange: setColumnSizing,
        onGlobalFilterChange: setGlobalFilterValue,
        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: enableSorting ? getSortedRowModel() : undefined,
        getFacetedRowModel: getFacetedRowModel(),
        getFacetedUniqueValues: getFacetedUniqueValues(),
        getGroupedRowModel: enableGrouping ? getGroupedRowModel() : undefined,
        getExpandedRowModel: enableGrouping ? getExpandedRowModel() : undefined,
        initialState: {
            pagination: { pageSize },
        },
    })

    // Export handlers
    const handleExport = (format: 'csv' | 'excel' | 'pdf') => {
        if (onExport) {
            onExport(format, {
                filename: `export-${new Date().toISOString().split('T')[0]}`,
                includeHeaders: true,
            })
            return
        }

        // Default CSV export
        if (format === 'csv') {
            const visibleColumns = table.getVisibleLeafColumns()
            const headers = visibleColumns.map(col => col.id).join(',')
            const rows = table.getFilteredRowModel().rows.map(row =>
                visibleColumns.map(col => {
                    const value = row.getValue(col.id)
                    // Escape CSV values
                    if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                        return `"${value.replace(/"/g, '""')}"`
                    }
                    return String(value ?? '')
                }).join(',')
            ).join('\n')

            const csv = `${headers}\n${rows}`
            const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `export-${new Date().toISOString().split('T')[0]}.csv`
            a.click()
            URL.revokeObjectURL(url)
        }
    }

    // Inline edit handlers
    const handleStartEdit = (rowId: string, columnId: string, value: unknown) => {
        if (!enableInlineEdit) return
        setEditingCell({ rowId, columnId, value })
    }

    const handleCancelEdit = () => {
        setEditingCell(null)
    }

    const handleSaveEdit = async () => {
        if (!editingCell || !onInlineEdit) return

        const row = table.getRow(editingCell.rowId)
        if (row) {
            await onInlineEdit(row.original, editingCell.columnId, editingCell.value)
        }
        setEditingCell(null)
    }

    // Render grouped row
    const renderGroupedRow = (row: Row<TData>) => {
        if (row.getIsGrouped()) {
            return (
                <TableRow key={row.id}>
                    <TableCell
                        colSpan={columns.length}
                        className="bg-muted/50 font-medium"
                    >
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 mr-2"
                            onClick={() => row.toggleExpanded()}
                        >
                            {row.getIsExpanded() ? (
                                <ChevronDown className="h-4 w-4" />
                            ) : (
                                <ChevronRight className="h-4 w-4" />
                            )}
                        </Button>
                        {row.groupingColumnId}: {String(row.groupingValue)} ({row.subRows.length})
                    </TableCell>
                </TableRow>
            )
        }
        return null
    }

    const isFiltered = table.getState().columnFilters.length > 0 || globalFilterValue !== ""

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
                                    : (table.getColumn(searchColumn ?? '')?.getFilterValue() as string) ?? ""
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
                    {/* Grouping Dropdown */}
                    {enableGrouping && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" size="sm" className="h-8">
                                    Gruppieren
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuLabel>Nach Spalte gruppieren</DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                {table.getAllColumns()
                                    .filter(col => col.columnDef.meta?.groupable !== false && col.getCanGroup())
                                    .map(column => (
                                        <DropdownMenuCheckboxItem
                                            key={column.id}
                                            checked={column.getIsGrouped()}
                                            onCheckedChange={() => column.toggleGrouping()}
                                        >
                                            {column.id}
                                        </DropdownMenuCheckboxItem>
                                    ))
                                }
                                {grouping.length > 0 && (
                                    <>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={() => table.resetGrouping()}>
                                            Gruppierung aufheben
                                        </DropdownMenuItem>
                                    </>
                                )}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}

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
                                {table.getAllColumns()
                                    .filter(col => col.getCanHide())
                                    .map(column => (
                                        <DropdownMenuCheckboxItem
                                            key={column.id}
                                            checked={column.getIsVisible()}
                                            onCheckedChange={(value) => column.toggleVisibility(!!value)}
                                        >
                                            {column.id}
                                        </DropdownMenuCheckboxItem>
                                    ))
                                }
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
                </div>
            </div>

            {/* Table */}
            <div className="rounded-md border overflow-hidden overflow-x-auto">
                <Table style={{ width: table.getCenterTotalSize() }}>
                    <TableHeader>
                        {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id}>
                                {headerGroup.headers.map((header) => {
                                    const isSortable = header.column.getCanSort()
                                    const sortDirection = header.column.getIsSorted()
                                    return (
                                        <TableHead
                                            key={header.id}
                                            colSpan={header.colSpan}
                                            className={cn(
                                                header.column.columnDef.meta?.className,
                                                enableColumnResizing && "relative"
                                            )}
                                            style={{
                                                width: header.getSize(),
                                            }}
                                            scope="col"
                                            aria-sort={
                                                isSortable
                                                    ? sortDirection === 'asc'
                                                        ? 'ascending'
                                                        : sortDirection === 'desc'
                                                            ? 'descending'
                                                            : 'none'
                                                    : undefined
                                            }
                                        >
                                            {header.isPlaceholder
                                                ? null
                                                : flexRender(
                                                    header.column.columnDef.header,
                                                    header.getContext()
                                                )}
                                            {/* Resize Handle */}
                                            {enableColumnResizing && (
                                                <div
                                                    onMouseDown={header.getResizeHandler()}
                                                    onTouchStart={header.getResizeHandler()}
                                                    className={cn(
                                                        "absolute right-0 top-0 h-full w-1 cursor-col-resize select-none touch-none",
                                                        header.column.getIsResizing() && "bg-primary"
                                                    )}
                                                >
                                                    <GripVertical className="h-4 w-4 opacity-0 hover:opacity-100" />
                                                </div>
                                            )}
                                        </TableHead>
                                    )
                                })}
                            </TableRow>
                        ))}
                    </TableHeader>
                    <TableBody>
                        {isLoading ? (
                            <TableRow>
                                <TableCell colSpan={columns.length} className="h-24 text-center">
                                    <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                                    <span className="mt-2 block text-muted-foreground">Laden...</span>
                                </TableCell>
                            </TableRow>
                        ) : table.getRowModel().rows?.length ? (
                            table.getRowModel().rows.map((row) => {
                                // Handle grouped rows
                                const groupedRow = enableGrouping ? renderGroupedRow(row) : null
                                if (groupedRow) return groupedRow

                                return (
                                    <TableRow
                                        key={row.id}
                                        data-state={row.getIsSelected() && "selected"}
                                        onClick={() => onRowClick?.(row.original)}
                                        className={cn(
                                            onRowClick && "cursor-pointer hover:bg-muted/50",
                                            compact && "h-8"
                                        )}
                                    >
                                        {row.getVisibleCells().map((cell) => {
                                            const isEditing = editingCell?.rowId === row.id &&
                                                editingCell?.columnId === cell.column.id
                                            const isEditable = enableInlineEdit &&
                                                cell.column.columnDef.meta?.editable

                                            return (
                                                <TableCell
                                                    key={cell.id}
                                                    className={cn(
                                                        cell.column.columnDef.meta?.className,
                                                        compact && "py-1"
                                                    )}
                                                    style={{
                                                        width: cell.column.getSize(),
                                                    }}
                                                    onDoubleClick={() => {
                                                        if (isEditable) {
                                                            handleStartEdit(
                                                                row.id,
                                                                cell.column.id,
                                                                cell.getValue()
                                                            )
                                                        }
                                                    }}
                                                >
                                                    {isEditing ? (
                                                        <EditableCell
                                                            value={editingCell.value}
                                                            onChange={(v) => setEditingCell(prev =>
                                                                prev ? { ...prev, value: v } : null
                                                            )}
                                                            onCancel={handleCancelEdit}
                                                            onSave={handleSaveEdit}
                                                        />
                                                    ) : (
                                                        flexRender(
                                                            cell.column.columnDef.cell,
                                                            cell.getContext()
                                                        )
                                                    )}
                                                </TableCell>
                                            )
                                        })}
                                    </TableRow>
                                )
                            })
                        ) : (
                            <TableRow>
                                <TableCell
                                    colSpan={columns.length}
                                    className="h-24 text-center"
                                >
                                    Keine Ergebnisse.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-2">
                <div className="flex-1 text-sm text-muted-foreground">
                    {enableRowSelection && (
                        <>
                            {table.getFilteredSelectedRowModel().rows.length} von{" "}
                            {table.getFilteredRowModel().rows.length} Zeile(n) ausgewählt.
                        </>
                    )}
                    {!enableRowSelection && (
                        <>
                            {table.getFilteredRowModel().rows.length} Einträge
                        </>
                    )}
                </div>
                <div className="flex items-center space-x-6 lg:space-x-8">
                    <div className="flex items-center space-x-2">
                        <p className="text-sm font-medium">Zeilen pro Seite</p>
                        <select
                            value={table.getState().pagination.pageSize}
                            onChange={(e) => table.setPageSize(Number(e.target.value))}
                            className="h-8 w-[70px] rounded-md border border-input bg-background px-2 text-sm"
                        >
                            {pageSizeOptions.map((size) => (
                                <option key={size} value={size}>
                                    {size}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="flex w-[100px] items-center justify-center text-sm font-medium">
                        Seite {table.getState().pagination.pageIndex + 1} von{" "}
                        {table.getPageCount()}
                    </div>
                    <div className="flex items-center space-x-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => table.setPageIndex(0)}
                            disabled={!table.getCanPreviousPage()}
                        >
                            {"<<"}
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => table.previousPage()}
                            disabled={!table.getCanPreviousPage()}
                        >
                            {"<"}
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => table.nextPage()}
                            disabled={!table.getCanNextPage()}
                        >
                            {">"}
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => table.setPageIndex(table.getPageCount() - 1)}
                            disabled={!table.getCanNextPage()}
                        >
                            {">>"}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}
