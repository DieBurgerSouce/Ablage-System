/**
 * Table Component - WCAG 2.1 AA Compliant
 *
 * Accessible table components with proper ARIA attributes.
 * Supports sorting indicators, loading states, and row selection.
 */
import * as React from "react"

import { cn } from "@/lib/utils"

// ==================== TYPES ====================

export type SortDirection = 'asc' | 'desc' | 'none';

interface TableProps extends React.HTMLAttributes<HTMLTableElement> {
    /** Accessible label describing the table content */
    ariaLabel?: string;
    /** Total row count for pagination accessibility */
    ariaRowCount?: number;
    /** Whether the table is loading data */
    isLoading?: boolean;
}

interface TableHeaderProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

interface TableBodyProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

interface TableFooterProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
    /** Row index for accessibility (1-based) */
    ariaRowIndex?: number;
    /** Whether this row is selected */
    isSelected?: boolean;
}

interface TableHeadProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
    /** Sort direction for sortable columns */
    sortDirection?: SortDirection;
    /** Whether this column is sortable */
    isSortable?: boolean;
}

interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {}

interface TableCaptionProps extends React.HTMLAttributes<HTMLTableCaptionElement> {}

// ==================== TABLE ====================

const Table = React.forwardRef<HTMLTableElement, TableProps>(
    ({ className, ariaLabel, ariaRowCount, isLoading, ...props }, ref) => (
        <div className="relative w-full overflow-auto">
            <table
                ref={ref}
                role="table"
                aria-label={ariaLabel}
                aria-rowcount={ariaRowCount}
                aria-busy={isLoading}
                className={cn("w-full caption-bottom text-sm", className)}
                {...props}
            />
        </div>
    )
)
Table.displayName = "Table"

// ==================== TABLE HEADER ====================

const TableHeader = React.forwardRef<HTMLTableSectionElement, TableHeaderProps>(
    ({ className, ...props }, ref) => (
        <thead
            ref={ref}
            role="rowgroup"
            className={cn("[&_tr]:border-b", className)}
            {...props}
        />
    )
)
TableHeader.displayName = "TableHeader"

// ==================== TABLE BODY ====================

const TableBody = React.forwardRef<HTMLTableSectionElement, TableBodyProps>(
    ({ className, ...props }, ref) => (
        <tbody
            ref={ref}
            role="rowgroup"
            className={cn("[&_tr:last-child]:border-0", className)}
            {...props}
        />
    )
)
TableBody.displayName = "TableBody"

// ==================== TABLE FOOTER ====================

const TableFooter = React.forwardRef<HTMLTableSectionElement, TableFooterProps>(
    ({ className, ...props }, ref) => (
        <tfoot
            ref={ref}
            role="rowgroup"
            className={cn(
                "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
                className
            )}
            {...props}
        />
    )
)
TableFooter.displayName = "TableFooter"

// ==================== TABLE ROW ====================

const TableRow = React.forwardRef<HTMLTableRowElement, TableRowProps>(
    ({ className, ariaRowIndex, isSelected, ...props }, ref) => (
        <tr
            ref={ref}
            role="row"
            aria-rowindex={ariaRowIndex}
            aria-selected={isSelected}
            data-state={isSelected ? "selected" : undefined}
            className={cn(
                "border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted",
                className
            )}
            {...props}
        />
    )
)
TableRow.displayName = "TableRow"

// ==================== TABLE HEAD (Column Header) ====================

const TableHead = React.forwardRef<HTMLTableCellElement, TableHeadProps>(
    ({ className, sortDirection, isSortable, ...props }, ref) => {
        // Map sort direction to ARIA sort value
        const ariaSort = isSortable
            ? sortDirection === 'asc'
                ? 'ascending'
                : sortDirection === 'desc'
                ? 'descending'
                : 'none'
            : undefined;

        return (
            <th
                ref={ref}
                role="columnheader"
                scope="col"
                aria-sort={ariaSort}
                className={cn(
                    "h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0",
                    isSortable && "cursor-pointer select-none hover:bg-muted/50",
                    className
                )}
                {...props}
            />
        );
    }
)
TableHead.displayName = "TableHead"

// ==================== TABLE CELL ====================

const TableCell = React.forwardRef<HTMLTableCellElement, TableCellProps>(
    ({ className, ...props }, ref) => (
        <td
            ref={ref}
            role="cell"
            className={cn(
                "p-4 align-middle [&:has([role=checkbox])]:pr-0",
                className
            )}
            {...props}
        />
    )
)
TableCell.displayName = "TableCell"

// ==================== TABLE CAPTION ====================

const TableCaption = React.forwardRef<HTMLTableCaptionElement, TableCaptionProps>(
    ({ className, ...props }, ref) => (
        <caption
            ref={ref}
            className={cn("mt-4 text-sm text-muted-foreground", className)}
            {...props}
        />
    )
)
TableCaption.displayName = "TableCaption"

// ==================== EXPORTS ====================

export {
    Table,
    TableHeader,
    TableBody,
    TableFooter,
    TableHead,
    TableRow,
    TableCell,
    TableCaption,
}

export type {
    TableProps,
    TableHeaderProps,
    TableBodyProps,
    TableFooterProps,
    TableRowProps,
    TableHeadProps,
    TableCellProps,
    TableCaptionProps,
}
