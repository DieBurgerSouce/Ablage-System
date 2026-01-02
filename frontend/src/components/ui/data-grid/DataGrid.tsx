"use client"

import * as React from "react"
import {
    type ColumnDef,
    type ColumnFiltersState,
    type SortingState,
    type VisibilityState,
    flexRender,
    getCoreRowModel,
    getFacetedRowModel,
    getFacetedUniqueValues,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    useReactTable,
    type OnChangeFn,
    type RowSelectionState,
    type RowData,
} from "@tanstack/react-table"

declare module '@tanstack/table-core' {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    interface ColumnMeta<TData extends RowData, TValue> {
        className?: string
    }
}

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { DataGridPagination } from "./DataGridPagination"
import { DataGridToolbar } from "./DataGridToolbar"

interface DataGridProps<TData, TValue> {
    columns: ColumnDef<TData, TValue>[]
    data: TData[]
    searchColumn?: string
    searchPlaceholder?: string

    // Controlled state (optional)
    sorting?: SortingState
    onSortingChange?: OnChangeFn<SortingState>
    rowSelection?: RowSelectionState
    onRowSelectionChange?: OnChangeFn<RowSelectionState>
    columnFilters?: ColumnFiltersState
    onColumnFiltersChange?: OnChangeFn<ColumnFiltersState>
}

export function DataGrid<TData, TValue>({
    columns,
    data,
    searchColumn,
    searchPlaceholder,
    sorting: controlledSorting,
    onSortingChange: setControlledSorting,
    rowSelection: controlledRowSelection,
    onRowSelectionChange: setControlledRowSelection,
    columnFilters: controlledColumnFilters,
    onColumnFiltersChange: setControlledColumnFilters,
}: DataGridProps<TData, TValue>) {
    const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({})
    const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
    const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
    const [sorting, setSorting] = React.useState<SortingState>([])

    const table = useReactTable({
        data,
        columns,
        state: {
            sorting: controlledSorting ?? sorting,
            columnVisibility,
            rowSelection: controlledRowSelection ?? rowSelection,
            columnFilters: controlledColumnFilters ?? columnFilters,
        },
        enableRowSelection: true,
        onRowSelectionChange: setControlledRowSelection ?? setRowSelection,
        onSortingChange: setControlledSorting ?? setSorting,
        onColumnFiltersChange: setControlledColumnFilters ?? setColumnFilters,
        onColumnVisibilityChange: setColumnVisibility,
        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFacetedRowModel: getFacetedRowModel(),
        getFacetedUniqueValues: getFacetedUniqueValues(),
    })

    return (
        <div className="space-y-4">
            <DataGridToolbar
                table={table}
                filterColumn={searchColumn}
                searchPlaceholder={searchPlaceholder}
            />
            <div className="rounded-md border overflow-hidden overflow-x-auto">
                <Table>
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
                                            className={header.column.columnDef.meta?.className}
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
                                        </TableHead>
                                    )
                                })}
                            </TableRow>
                        ))}
                    </TableHeader>
                    <TableBody>
                        {table.getRowModel().rows?.length ? (
                            table.getRowModel().rows.map((row) => (
                                <TableRow
                                    key={row.id}
                                    data-state={row.getIsSelected() && "selected"}
                                >
                                    {row.getVisibleCells().map((cell) => (
                                        <TableCell
                                            key={cell.id}
                                            className={cell.column.columnDef.meta?.className}
                                        >
                                            {flexRender(
                                                cell.column.columnDef.cell,
                                                cell.getContext()
                                            )}
                                        </TableCell>
                                    ))}
                                </TableRow>
                            ))
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
            <DataGridPagination table={table} />
        </div>
    )
}
