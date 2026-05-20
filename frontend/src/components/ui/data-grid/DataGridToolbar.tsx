
"use client"

import type { Table } from "@tanstack/react-table"
import { X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { DataGridViewOptions } from "./DataGridViewOptions"

interface DataGridToolbarProps<TData> {
    table: Table<TData>
    filterColumn?: string
    searchPlaceholder?: string
}

export function DataGridToolbar<TData>({
    table,
    filterColumn = "title",
    searchPlaceholder = "Filtern...",
}: DataGridToolbarProps<TData>) {
    const isFiltered = table.getState().columnFilters.length > 0

    return (
        <div className="flex items-center justify-between">
            <div className="flex flex-1 items-center space-x-2">
                <Input
                    placeholder={searchPlaceholder}
                    value={(table.getColumn(filterColumn)?.getFilterValue() as string) ?? ""}
                    onChange={(event) =>
                        table.getColumn(filterColumn)?.setFilterValue(event.target.value)
                    }
                    className="h-8 w-[150px] lg:w-[250px]"
                />
                {isFiltered && (
                    <Button
                        variant="ghost"
                        onClick={() => table.resetColumnFilters()}
                        className="h-8 px-2 lg:px-3"
                    >
                        Zurücksetzen
                        <X className="ml-2 h-4 w-4" />
                    </Button>
                )}
            </div>
            <DataGridViewOptions table={table} />
        </div>
    )
}
