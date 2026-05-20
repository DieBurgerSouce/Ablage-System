/**
 * FinanceCategoryDocumentList - Dokumentenliste für Finanz-Kategorien
 *
 * Zeigt Dokumente einer Finanz-Kategorie (z.B. Steuerbescheide, Lohn/Gehalt).
 * Analog zu CategoryDocumentList, aber mit Finanz-spezifischen Features.
 *
 * Route: /finanzen/$year/$category
 */

import { useState, useCallback, useMemo } from 'react'
import { useParams, Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, Upload, Calendar, AlertTriangle, Search, Filter, ShieldAlert } from 'lucide-react'
import * as LucideIcons from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  getFinanceCategoryById,
  categoryHasDeadlines,
  categoryHasAmounts,
} from '../types'
import { useFinanceCategoryPage, DEFAULT_FINANCE_CATEGORY_FILTER, useInvalidateFinanceQueries } from '../hooks/use-finanzen-queries'
import { formatDate, formatCurrency } from '../utils/format'
import { FinanceDocumentUploadDialog } from './FinanceDocumentUploadDialog'
import { FinanceDocumentEditDialog } from './FinanceDocumentEditDialog'
import { FinanceFilterDialog, type FilterValues } from './FinanceFilterDialog'
import { FinanceDocumentCardList } from './FinanceDocumentCard'
import { FinanceDocumentTableSkeleton } from './FinanceSkeleton'
import { FinanceErrorCard, classifyError } from './FinanceErrorBoundary'
import { FinanceBulkActionsBar } from './FinanceBulkActionsBar'
import { FinanceMultiFileUpload } from './FinanceMultiFileUpload'
import { useResponsiveBreakpoints } from '@/lib/hooks/use-media-query'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ChevronDown, Files } from 'lucide-react'
import type { FinanceCategoryDocument } from '@/lib/api/services/finance'

/**
 * Icon-Komponente die dynamisch Lucide Icons rendert
 */
function DynamicIcon({ name, className }: { name: string; className?: string }) {
  const IconComponent = (LucideIcons as unknown as Record<string, React.ComponentType<{ className?: string }>>)[name]
  if (!IconComponent) {
    return <FolderOpen className={className} />
  }
  return <IconComponent className={className} />
}

export function FinanceCategoryDocumentList() {
  const params = useParams({ strict: false })
  const navigate = useNavigate()
  const yearId = params.year
  const categoryId = params.category

  // Responsive Breakpoints
  const { isMobile, isTablet } = useResponsiveBreakpoints()

  // Search and pagination state
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(0)

  // Filter state
  const [filters, setFilters] = useState<FilterValues>({
    sortBy: 'document_date',
    sortOrder: 'desc',
  })

  // Dialog state
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [multiUploadDialogOpen, setMultiUploadDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [filterDialogOpen, setFilterDialogOpen] = useState(false)
  const [selectedDocument, setSelectedDocument] = useState<FinanceCategoryDocument | null>(null)

  // Multi-Select State
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Query Invalidation für Bulk Actions
  const { invalidateCategoryDocuments } = useInvalidateFinanceQueries()

  // Get category info
  const categoryInfo = categoryId ? getFinanceCategoryById(categoryId) : null

  const showAmounts = categoryId ? categoryHasAmounts(categoryId) : false
  const showDeadlines = categoryId ? categoryHasDeadlines(categoryId) : false

  // Use API hook with filters
  const { documents, aggregations, isLoading, isError, error } = useFinanceCategoryPage(
    yearId,
    categoryId,
    {
      ...DEFAULT_FINANCE_CATEGORY_FILTER,
      search: searchQuery || undefined,
      dateFrom: filters.dateFrom,
      dateTo: filters.dateTo,
      amountMin: filters.amountMin,
      amountMax: filters.amountMax,
      steuerart: filters.steuerart,
      sortBy: filters.sortBy,
      sortOrder: filters.sortOrder,
      page,
    }
  )

  // Handlers
  const handleDocumentClick = useCallback((doc: FinanceCategoryDocument) => {
    setSelectedDocument(doc)
    setEditDialogOpen(true)
  }, [])

  const handleFilterApply = useCallback((newFilters: FilterValues) => {
    setFilters(newFilters)
    setPage(0) // Reset to first page on filter change
  }, [])

  // Count active filters
  const activeFilterCount = [
    filters.dateFrom,
    filters.dateTo,
    filters.amountMin,
    filters.amountMax,
    filters.steuerart,
  ].filter(Boolean).length

  // Multi-Select Handlers
  const handleToggleSelect = useCallback((docId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(docId)) {
        next.delete(docId)
      } else {
        next.add(docId)
      }
      return next
    })
  }, [])

  const handleToggleSelectAll = useCallback(() => {
    if (!documents?.items) return
    const allIds = documents.items.map((doc) => doc.id)
    const allSelected = allIds.every((id) => selectedIds.has(id))

    if (allSelected) {
      // Deselect all
      setSelectedIds(new Set())
    } else {
      // Select all visible
      setSelectedIds(new Set(allIds))
    }
  }, [documents?.items, selectedIds])

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const handleBulkActionComplete = useCallback(() => {
    setSelectedIds(new Set())
    if (yearId && categoryId) {
      invalidateCategoryDocuments(yearId, categoryId)
    }
  }, [yearId, categoryId, invalidateCategoryDocuments])

  // Compute selection state
  const allSelected = useMemo(() => {
    if (!documents?.items?.length) return false
    return documents.items.every((doc) => selectedIds.has(doc.id))
  }, [documents?.items, selectedIds])

  const someSelected = useMemo(() => {
    if (!documents?.items?.length) return false
    return documents.items.some((doc) => selectedIds.has(doc.id)) && !allSelected
  }, [documents?.items, selectedIds, allSelected])

  // Loading state - Enterprise-grade Skeleton
  if (isLoading) {
    return (
      <div className="p-8">
        <FinanceDocumentTableSkeleton rows={isMobile ? 3 : 5} />
      </div>
    )
  }

  // Error state - Enterprise-grade Error Card
  if (isError) {
    const classifiedError = classifyError(error)
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <FinanceErrorCard
          error={classifiedError}
          onRetry={classifiedError.retryable ? () => window.location.reload() : undefined}
          onGoHome={() => navigate({ to: '/finanzen' })}
        />
      </div>
    )
  }

  // Not found state
  if (!categoryInfo) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <h2 className="text-xl font-semibold text-muted-foreground">Kategorie nicht gefunden</h2>
          <Button variant="link" onClick={() => navigate({ to: '/finanzen' })}>
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    )
  }

  const documentCount = aggregations?.totalDocuments ?? documents.total
  const filteredDocuments = documents.items

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to="/finanzen/$year" params={{ year: yearId! }}>
          <Button variant="ghost" size="icon" aria-label="Zurück zum Jahr">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to="/finanzen" className="hover:text-foreground transition-colors">
              Finanzen
            </Link>
            <span>/</span>
            <Link to="/finanzen/$year" params={{ year: yearId! }} className="hover:text-foreground transition-colors">
              {yearId}
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/30">
              <DynamicIcon name={categoryInfo.icon} className="w-6 h-6 text-emerald-500" />
            </div>
            {categoryInfo.label}
            {categoryInfo.shortCode && (
              <Badge variant="outline" className="text-sm">
                {categoryInfo.shortCode}
              </Badge>
            )}
          </h1>
        </div>
      </div>

      {/* Stats */}
      <div className="flex flex-wrap gap-4">
        <Badge variant="secondary" className="text-sm py-1.5 px-3">
          <FileText className="w-4 h-4 mr-2" />
          {documentCount} Dokumente
        </Badge>
        <Badge variant="outline" className="text-sm py-1.5 px-3">
          <Calendar className="w-4 h-4 mr-2" />
          Jahr {yearId}
        </Badge>
        {aggregations && showAmounts && (aggregations.totalNachzahlung > 0 || aggregations.totalErstattung > 0) && (
          <>
            {aggregations.totalNachzahlung > 0 && (
              <Badge variant="outline" className="text-sm py-1.5 px-3 bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-800">
                Nachzahlung: {formatCurrency(aggregations.totalNachzahlung)}
              </Badge>
            )}
            {aggregations.totalErstattung > 0 && (
              <Badge variant="outline" className="text-sm py-1.5 px-3 bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800">
                Erstattung: {formatCurrency(aggregations.totalErstattung)}
              </Badge>
            )}
          </>
        )}
        {aggregations && showDeadlines && aggregations.pendingDeadlines > 0 && (
          <Badge variant="outline" className="text-sm py-1.5 px-3 bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-800">
            {aggregations.pendingDeadlines} offene Fristen
          </Badge>
        )}
      </div>

      {/* Search & Filter Bar - Responsive */}
      <div className="flex flex-col sm:flex-row gap-3 sm:gap-4">
        <div className="relative flex-1 sm:max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Dokumente suchen..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setPage(0) // Reset to first page on search
            }}
            className="pl-9"
            aria-label="Dokumente suchen"
          />
        </div>
        <div className="flex gap-2 sm:gap-4">
          <Button
            variant="outline"
            className="gap-2 flex-1 sm:flex-none"
            onClick={() => setFilterDialogOpen(true)}
            aria-label={`Filter ${activeFilterCount > 0 ? `(${activeFilterCount} aktiv)` : ''}`}
          >
            <Filter className="w-4 h-4" />
            {!isMobile && 'Filter'}
            {activeFilterCount > 0 && (
              <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-xs">
                {activeFilterCount}
              </Badge>
            )}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button className="gap-2 flex-1 sm:flex-none" aria-label="Dokument hochladen">
                <Upload className="w-4 h-4" />
                {!isMobile && 'Hochladen'}
                <ChevronDown className="w-3 h-3 ml-1" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setUploadDialogOpen(true)}>
                <Upload className="w-4 h-4 mr-2" />
                Einzelne Datei
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setMultiUploadDialogOpen(true)}>
                <Files className="w-4 h-4 mr-2" />
                Mehrere Dateien
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Documents - Responsive: Cards auf Mobile, Tabelle auf Desktop */}
      {filteredDocuments.length > 0 ? (
        isMobile ? (
          // Mobile: Card-Ansicht
          <FinanceDocumentCardList
            documents={filteredDocuments}
            showAmounts={showAmounts}
            showDeadlines={showDeadlines}
            onDocumentClick={handleDocumentClick}
          />
        ) : (
          // Tablet/Desktop: Tabellen-Ansicht mit horizontalem Scroll auf Tablet
          <Card>
            <CardContent className="p-0">
              <div className={isTablet ? 'overflow-x-auto' : ''}>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[50px]">
                        <Checkbox
                          checked={allSelected}
                          ref={(el) => {
                            if (el) {
                              (el as HTMLButtonElement & { indeterminate: boolean }).indeterminate = someSelected
                            }
                          }}
                          onCheckedChange={handleToggleSelectAll}
                          aria-label="Alle auswählen"
                        />
                      </TableHead>
                      <TableHead className="min-w-[200px]">Dateiname</TableHead>
                      <TableHead className="min-w-[100px]">Datum</TableHead>
                      {showAmounts && <TableHead className="text-right min-w-[150px]">Betrag</TableHead>}
                      {showDeadlines && <TableHead className="min-w-[120px]">Aktenzeichen</TableHead>}
                      {showDeadlines && <TableHead className="min-w-[140px]">Einspruchsfrist</TableHead>}
                      <TableHead className="min-w-[100px]">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredDocuments.map((doc) => (
                      <TableRow
                        key={doc.id}
                        className={`cursor-pointer hover:bg-muted/50 ${selectedIds.has(doc.id) ? 'bg-muted/30' : ''}`}
                        data-selected={selectedIds.has(doc.id)}
                      >
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={selectedIds.has(doc.id)}
                            onCheckedChange={() => handleToggleSelect(doc.id)}
                            aria-label={`${doc.originalFilename || doc.filename} auswählen`}
                          />
                        </TableCell>
                        <TableCell
                          className="font-medium"
                          onClick={() => handleDocumentClick(doc)}
                          tabIndex={0}
                          role="button"
                          aria-label={`Dokument: ${doc.originalFilename || doc.filename}${doc.hasAnomalies ? ' (Anomalie erkannt)' : ''}`}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault()
                              handleDocumentClick(doc)
                            }
                          }}
                        >
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                            <span className="truncate max-w-[250px]">
                              {doc.originalFilename || doc.filename}
                            </span>
                            {doc.hasAnomalies && (
                              <Badge
                                variant="outline"
                                className="ml-1 gap-1 px-1.5 py-0 text-xs bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/50 dark:text-amber-400 dark:border-amber-700"
                                title={`${doc.anomalyCount} Anomalie${doc.anomalyCount !== 1 ? 'n' : ''} erkannt${doc.riskScore ? ` (${Math.round(doc.riskScore * 100)}% Risiko)` : ''}`}
                              >
                                <ShieldAlert className="w-3 h-3" />
                                {doc.anomalyCount}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{formatDate(doc.documentDate || doc.createdAt)}</TableCell>
                        {showAmounts && (
                          <TableCell className="text-right font-mono">
                            {doc.totalAmount ? formatCurrency(doc.totalAmount) : '-'}
                            {doc.nachzahlung && (
                              <span className="text-red-600 dark:text-red-400 ml-2">
                                -{formatCurrency(doc.nachzahlung)}
                              </span>
                            )}
                            {doc.erstattung && (
                              <span className="text-green-600 dark:text-green-400 ml-2">
                                +{formatCurrency(doc.erstattung)}
                              </span>
                            )}
                          </TableCell>
                        )}
                        {showDeadlines && (
                          <TableCell className="font-mono text-sm">
                            {doc.aktenzeichen || '-'}
                          </TableCell>
                        )}
                        {showDeadlines && (
                          <TableCell>
                            {doc.einspruchsfrist ? (
                              <div className="flex items-center gap-2">
                                {new Date(doc.einspruchsfrist) < new Date() ? (
                                  <Badge variant="destructive" className="gap-1">
                                    <AlertTriangle className="w-3 h-3" />
                                    Abgelaufen
                                  </Badge>
                                ) : (
                                  <span>{formatDate(doc.einspruchsfrist)}</span>
                                )}
                              </div>
                            ) : (
                              '-'
                            )}
                          </TableCell>
                        )}
                        <TableCell>
                          <Badge
                            variant={doc.processingStatus === 'completed' ? 'secondary' : 'outline'}
                            className={doc.processingStatus === 'completed' ? '' : 'bg-amber-50 text-amber-700 border-amber-200'}
                          >
                            {doc.processingStatus === 'completed' ? 'Verarbeitet' : 'Ausstehend'}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )
      ) : (
        // Empty State
        <Card>
          <CardContent className="p-0">
            <div className="flex flex-col items-center justify-center py-12 text-center px-4">
              <FileText className="w-12 h-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium mb-2">Keine Dokumente gefunden</h3>
              <p className="text-muted-foreground mb-4 max-w-md">
                {searchQuery
                  ? 'Keine Dokumente entsprechen Ihrer Suche'
                  : `Es wurden noch keine ${categoryInfo.label} hochgeladen`}
              </p>
              <Button className="gap-2" onClick={() => setUploadDialogOpen(true)}>
                <Upload className="w-4 h-4" />
                Dokument hochladen
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Pagination - Responsive */}
      {documents.totalPages > 1 && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground text-center sm:text-left">
            {isMobile ? (
              `${page + 1} / ${documents.totalPages}`
            ) : (
              `Zeige ${filteredDocuments.length} von ${documents.total} Dokumenten (Seite ${page + 1} von ${documents.totalPages})`
            )}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              aria-label="Vorherige Seite"
            >
              Zurück
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.min(documents.totalPages - 1, p + 1))}
              disabled={page >= documents.totalPages - 1}
              aria-label="Nächste Seite"
            >
              Weiter
            </Button>
          </div>
        </div>
      )}

      {/* Quick Upload */}
      <Card className="border-dashed">
        <CardContent className="flex items-center justify-center py-8">
          <Button variant="outline" className="gap-2" onClick={() => setUploadDialogOpen(true)}>
            <Upload className="w-4 h-4" />
            Dokument zu {categoryInfo.label} hochladen
          </Button>
        </CardContent>
      </Card>

      {/* Dialogs */}
      <FinanceDocumentUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        yearId={yearId!}
        categoryId={categoryId!}
      />

      <FinanceMultiFileUpload
        open={multiUploadDialogOpen}
        onOpenChange={setMultiUploadDialogOpen}
        yearId={yearId!}
        categoryId={categoryId!}
      />

      <FinanceDocumentEditDialog
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        document={selectedDocument}
        yearId={yearId!}
        categoryId={categoryId!}
      />

      <FinanceFilterDialog
        open={filterDialogOpen}
        onOpenChange={setFilterDialogOpen}
        categoryId={categoryId!}
        currentFilters={filters}
        onApplyFilters={handleFilterApply}
      />

      {/* Bulk Actions Bar */}
      <FinanceBulkActionsBar
        selectedIds={Array.from(selectedIds)}
        onClearSelection={handleClearSelection}
        onActionComplete={handleBulkActionComplete}
        currentYear={yearId}
        currentCategory={categoryId}
      />
    </div>
  )
}
