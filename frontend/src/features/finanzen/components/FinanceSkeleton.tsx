/**
 * FinanceSkeleton - Enterprise-grade Skeleton Loading Components
 *
 * Varianten:
 * - Dashboard: KPI-Cards + Jahres-Grid
 * - YearGrid: Kategorie-Karten Grid
 * - DocumentTable: Dokument-Tabelle
 * - DocumentCard: Einzelne Dokument-Card (Mobile)
 * - Aggregations: KPI-Statistiken
 */

import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// ==================== SKELETON VARIANTS ====================

/**
 * Dashboard-Skeleton für die Hauptseite
 */
export function FinanceDashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse" role="status" aria-label="Lade Finanzen-Dashboard...">
      {/* Header */}
      <div className="space-y-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <FinanceKPICardSkeleton key={i} />
        ))}
      </div>

      {/* Tags */}
      <div className="flex gap-2">
        <Skeleton className="h-6 w-20 rounded-full" />
        <Skeleton className="h-6 w-28 rounded-full" />
      </div>

      {/* Year Grid or Empty State */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <FinanceYearCardSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}

/**
 * KPI-Card Skeleton (Einzelne Statistik-Card)
 */
export function FinanceKPICardSkeleton() {
  return (
    <Card className="bg-muted/30">
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Jahr-Card Skeleton
 */
export function FinanceYearCardSkeleton() {
  return (
    <Card className="bg-muted/20">
      <CardHeader className="pb-2">
        <div className="flex justify-between items-center">
          <Skeleton className="h-6 w-16" />
          <Skeleton className="h-5 w-12 rounded-full" />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <Skeleton className="h-4 w-4" />
              <Skeleton className="h-4 w-12" />
            </div>
          ))}
        </div>
        <Skeleton className="h-8 w-full" />
      </CardContent>
    </Card>
  )
}

/**
 * Kategorie-Grid Skeleton (Jahr-Detail-Seite)
 */
export function FinanceCategoryGridSkeleton() {
  return (
    <div className="space-y-6 animate-pulse" role="status" aria-label="Lade Kategorien...">
      {/* Header mit Back-Button */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-10 w-10 rounded" />
        <div className="space-y-2">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <FinanceKPICardSkeleton key={i} />
        ))}
      </div>

      {/* Package Sections */}
      {[...Array(4)].map((_, packageIndex) => (
        <div key={packageIndex} className="space-y-3">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-5 rounded" />
            <Skeleton className="h-5 w-24" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {[...Array(4)].map((_, i) => (
              <FinanceCategoryCardSkeleton key={i} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Kategorie-Card Skeleton
 */
export function FinanceCategoryCardSkeleton() {
  return (
    <Card className="bg-muted/20">
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-8 rounded" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Dokument-Tabelle Skeleton
 */
export function FinanceDocumentTableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-4 animate-pulse" role="status" aria-label="Lade Dokumente...">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10 rounded" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-48" />
          </div>
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-10 w-24" />
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <FinanceKPICardSkeleton key={i} />
        ))}
      </div>

      {/* Search & Filter Row */}
      <div className="flex gap-4">
        <Skeleton className="h-10 flex-1 max-w-md" />
        <Skeleton className="h-10 w-24" />
        <Skeleton className="h-10 w-32" />
      </div>

      {/* Table Header */}
      <div className="border rounded-lg">
        <div className="grid grid-cols-6 gap-4 p-4 border-b bg-muted/30">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>

        {/* Table Rows */}
        {[...Array(rows)].map((_, rowIndex) => (
          <div
            key={rowIndex}
            className={cn(
              "grid grid-cols-6 gap-4 p-4",
              rowIndex < rows - 1 && "border-b"
            )}
          >
            {[...Array(6)].map((_, colIndex) => (
              <Skeleton
                key={colIndex}
                className={cn(
                  "h-4",
                  colIndex === 0 && "w-32",
                  colIndex === 1 && "w-24",
                  colIndex === 2 && "w-20",
                  colIndex === 3 && "w-16",
                  colIndex === 4 && "w-24",
                  colIndex === 5 && "w-20"
                )}
              />
            ))}
          </div>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-4 w-32" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
          <Skeleton className="h-8 w-8" />
        </div>
      </div>
    </div>
  )
}

/**
 * Dokument-Card Skeleton (Mobile)
 */
export function FinanceDocumentCardSkeleton() {
  return (
    <Card className="bg-muted/20">
      <CardContent className="p-4 space-y-3">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded" />
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
        <div className="flex gap-4">
          <div className="space-y-1">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-4 w-20" />
          </div>
          <div className="space-y-1">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-4 w-24" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Aggregations-Skeleton (Statistik-Bereich)
 */
export function FinanceAggregationsSkeleton() {
  return (
    <div
      className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse"
      role="status"
      aria-label="Lade Statistiken..."
    >
      {[...Array(4)].map((_, i) => (
        <FinanceKPICardSkeleton key={i} />
      ))}
    </div>
  )
}

/**
 * Inline Loading Indicator
 */
export function FinanceLoadingSpinner({ size = 'md', className = '' }: { size?: 'sm' | 'md' | 'lg', className?: string }) {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-6 w-6',
    lg: 'h-8 w-8',
  }

  return (
    <div className={cn("flex items-center justify-center", className)} role="status" aria-label="Laden...">
      <svg
        className={cn("animate-spin text-primary", sizeClasses[size])}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <span className="sr-only">Laden...</span>
    </div>
  )
}

/**
 * Full-Page Loading State
 */
export function FinanceFullPageLoader() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <FinanceLoadingSpinner size="lg" />
      <p className="text-muted-foreground">Finanzdaten werden geladen...</p>
    </div>
  )
}

export default {
  Dashboard: FinanceDashboardSkeleton,
  CategoryGrid: FinanceCategoryGridSkeleton,
  DocumentTable: FinanceDocumentTableSkeleton,
  DocumentCard: FinanceDocumentCardSkeleton,
  Aggregations: FinanceAggregationsSkeleton,
  KPICard: FinanceKPICardSkeleton,
  YearCard: FinanceYearCardSkeleton,
  CategoryCard: FinanceCategoryCardSkeleton,
  Spinner: FinanceLoadingSpinner,
  FullPage: FinanceFullPageLoader,
}
