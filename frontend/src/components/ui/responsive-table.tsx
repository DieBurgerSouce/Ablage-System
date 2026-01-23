/**
 * Responsive Table Component
 *
 * Mobile-optimierte Tabelle die auf kleinen Bildschirmen
 * als Card-Layout dargestellt wird.
 */

import * as React from 'react'
import { cn } from '@/lib/utils'
import { useScreenSize } from '@/lib/mobile'
import { Card, CardContent } from './card'

// =============================================================================
// Context
// =============================================================================

interface ResponsiveTableContextValue {
  isMobile: boolean
  headers: string[]
}

const ResponsiveTableContext = React.createContext<ResponsiveTableContextValue>({
  isMobile: false,
  headers: [],
})

// =============================================================================
// ResponsiveTable
// =============================================================================

interface ResponsiveTableProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Column headers for mobile card labels */
  headers?: string[]
  /** Force mobile layout regardless of screen size */
  forceMobile?: boolean
}

const ResponsiveTable = React.forwardRef<HTMLDivElement, ResponsiveTableProps>(
  ({ className, children, headers = [], forceMobile = false, ...props }, ref) => {
    const { isMobile: screenIsMobile } = useScreenSize()
    const isMobile = forceMobile || screenIsMobile

    return (
      <ResponsiveTableContext.Provider value={{ isMobile, headers }}>
        <div
          ref={ref}
          className={cn('w-full', className)}
          {...props}
        >
          {isMobile ? (
            <div className="space-y-3">{children}</div>
          ) : (
            <div className="relative w-full overflow-auto">
              <table className="w-full caption-bottom text-sm">
                {children}
              </table>
            </div>
          )}
        </div>
      </ResponsiveTableContext.Provider>
    )
  }
)
ResponsiveTable.displayName = 'ResponsiveTable'

// =============================================================================
// ResponsiveTableHeader
// =============================================================================

interface ResponsiveTableHeaderProps
  extends React.HTMLAttributes<HTMLTableSectionElement> {}

const ResponsiveTableHeader = React.forwardRef<
  HTMLTableSectionElement,
  ResponsiveTableHeaderProps
>(({ className, children, ...props }, ref) => {
  const { isMobile } = React.useContext(ResponsiveTableContext)

  if (isMobile) {
    // Headers are hidden on mobile, shown as labels in each card
    return null
  }

  return (
    <thead ref={ref} className={cn('[&_tr]:border-b', className)} {...props}>
      {children}
    </thead>
  )
})
ResponsiveTableHeader.displayName = 'ResponsiveTableHeader'

// =============================================================================
// ResponsiveTableBody
// =============================================================================

interface ResponsiveTableBodyProps
  extends React.HTMLAttributes<HTMLTableSectionElement> {}

const ResponsiveTableBody = React.forwardRef<
  HTMLTableSectionElement,
  ResponsiveTableBodyProps
>(({ className, children, ...props }, ref) => {
  const { isMobile } = React.useContext(ResponsiveTableContext)

  if (isMobile) {
    // Use role="list" for accessibility - screen readers understand card lists
    return (
      <div
        ref={ref as React.Ref<HTMLDivElement>}
        role="list"
        aria-label="Tabelleneinträge"
        className={cn('space-y-3', className)}
      >
        {children}
      </div>
    )
  }

  return (
    <tbody
      ref={ref}
      className={cn('[&_tr:last-child]:border-0', className)}
      {...props}
    >
      {children}
    </tbody>
  )
})
ResponsiveTableBody.displayName = 'ResponsiveTableBody'

// =============================================================================
// ResponsiveTableRow
// =============================================================================

interface ResponsiveTableRowProps
  extends React.HTMLAttributes<HTMLTableRowElement> {
  /** Click handler for the entire row */
  onRowClick?: () => void
}

const ResponsiveTableRow = React.forwardRef<
  HTMLTableRowElement,
  ResponsiveTableRowProps
>(({ className, children, onRowClick, ...props }, ref) => {
  const { isMobile, headers } = React.useContext(ResponsiveTableContext)

  if (isMobile) {
    // Convert children (TableCell) to card layout
    const cells = React.Children.toArray(children)

    return (
      <Card
        role="listitem"
        className={cn(
          'cursor-pointer hover:bg-accent/50 transition-colors',
          'active:scale-[0.99] touch-manipulation',
          className
        )}
        onClick={onRowClick}
        tabIndex={onRowClick ? 0 : undefined}
        onKeyDown={onRowClick ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onRowClick()
          }
        } : undefined}
      >
        <CardContent className="p-4 space-y-2">
          {cells.map((cell, index) => {
            if (!React.isValidElement(cell)) return null
            // Type-safe extraction of cell props
            const cellProps = cell.props as ResponsiveTableCellProps & {
              children?: React.ReactNode
              className?: string
            }
            const { children: cellContent, className: cellClassName, mobileLabel } = cellProps
            // Use mobileLabel if provided, otherwise fall back to header from context
            const label = mobileLabel ?? headers[index] ?? ''
            const labelId = label ? `cell-label-${index}` : undefined

            return (
              <div
                key={index}
                className="flex justify-between items-start gap-4"
                role="group"
                aria-labelledby={labelId}
              >
                {label && (
                  <span
                    id={labelId}
                    className="text-sm text-muted-foreground font-medium min-w-[100px]"
                  >
                    {label}
                  </span>
                )}
                <span className={cn('text-sm text-right flex-1', cellClassName)}>
                  {cellContent}
                </span>
              </div>
            )
          })}
        </CardContent>
      </Card>
    )
  }

  return (
    <tr
      ref={ref}
      className={cn(
        'border-b transition-colors hover:bg-muted/50 data-[state=selected]:bg-muted',
        onRowClick && 'cursor-pointer',
        className
      )}
      onClick={onRowClick}
      {...props}
    >
      {children}
    </tr>
  )
})
ResponsiveTableRow.displayName = 'ResponsiveTableRow'

// =============================================================================
// ResponsiveTableHead
// =============================================================================

interface ResponsiveTableHeadProps
  extends React.ThHTMLAttributes<HTMLTableCellElement> {}

const ResponsiveTableHead = React.forwardRef<
  HTMLTableCellElement,
  ResponsiveTableHeadProps
>(({ className, children, ...props }, ref) => {
  const { isMobile } = React.useContext(ResponsiveTableContext)

  if (isMobile) {
    return null
  }

  return (
    <th
      ref={ref}
      className={cn(
        'h-12 px-4 text-left align-middle font-medium text-muted-foreground [&:has([role=checkbox])]:pr-0',
        className
      )}
      {...props}
    >
      {children}
    </th>
  )
})
ResponsiveTableHead.displayName = 'ResponsiveTableHead'

// =============================================================================
// ResponsiveTableCell
// =============================================================================

interface ResponsiveTableCellProps
  extends React.TdHTMLAttributes<HTMLTableCellElement> {
  /** Label shown on mobile (overrides header from context) */
  mobileLabel?: string
}

const ResponsiveTableCell = React.forwardRef<
  HTMLTableCellElement,
  ResponsiveTableCellProps
>(({ className, children, mobileLabel: _mobileLabel, ...props }, ref) => {
  // mobileLabel is extracted here to prevent it from being passed to <td>
  // It is read from cell.props in ResponsiveTableRow for mobile rendering
  const { isMobile } = React.useContext(ResponsiveTableContext)

  if (isMobile) {
    // Rendered inside ResponsiveTableRow - mobileLabel is read from props there
    return <>{children}</>
  }

  return (
    <td
      ref={ref}
      className={cn('p-4 align-middle [&:has([role=checkbox])]:pr-0', className)}
      {...props}
    >
      {children}
    </td>
  )
})
ResponsiveTableCell.displayName = 'ResponsiveTableCell'

// =============================================================================
// ResponsiveTableCaption
// =============================================================================

interface ResponsiveTableCaptionProps
  extends React.HTMLAttributes<HTMLTableCaptionElement> {}

const ResponsiveTableCaption = React.forwardRef<
  HTMLTableCaptionElement,
  ResponsiveTableCaptionProps
>(({ className, children, ...props }, ref) => {
  const { isMobile } = React.useContext(ResponsiveTableContext)

  if (isMobile) {
    return (
      <div className={cn('text-sm text-muted-foreground text-center py-4', className)}>
        {children}
      </div>
    )
  }

  return (
    <caption
      ref={ref}
      className={cn('mt-4 text-sm text-muted-foreground', className)}
      {...props}
    >
      {children}
    </caption>
  )
})
ResponsiveTableCaption.displayName = 'ResponsiveTableCaption'

// =============================================================================
// Exports
// =============================================================================

export {
  ResponsiveTable,
  ResponsiveTableHeader,
  ResponsiveTableBody,
  ResponsiveTableRow,
  ResponsiveTableHead,
  ResponsiveTableCell,
  ResponsiveTableCaption,
}
