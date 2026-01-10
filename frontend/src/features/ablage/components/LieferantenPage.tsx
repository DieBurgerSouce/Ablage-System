import { useState, useMemo, useEffect, useCallback, memo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Package, FolderOpen, ChevronRight, FileText, AlertCircle, Loader2, Search, ChevronDown, ArrowUpNarrowWide, ArrowDownWideNarrow } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { fetchSuppliersForFrontend, type SupplierForFrontend, type PaginatedEntityResponse, type SupplierSortField } from '../api/ablage-api'

const PAGE_SIZE = 100

/**
 * Separate SearchInput component to prevent re-renders from query state changes
 */
const SearchInput = memo(function SearchInput({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="relative max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <Input
        placeholder="Suche nach Lieferantenname..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pl-10"
      />
    </div>
  )
})

/**
 * LieferantenPage - Zeigt Lieferanten als klickbare Ordner-Cards mit Suche und Pagination
 *
 * Klick auf einen Lieferanten navigiert zur Ordner-Auswahl (Spargelmesser/Folie)
 * Display-Format: Nur Matchcode (KEINE Nummer - weil Nummern chaotisch)
 *
 * Route: /lieferanten
 */
export function LieferantenPage() {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState<SupplierSortField>('name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')

  // Stable callback for search input
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value)
  }, [])

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const {
    data,
    isLoading,
    isFetching,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['suppliers', debouncedSearch, sortBy, sortOrder],
    queryFn: async ({ pageParam = 1 }) => {
      return fetchSuppliersForFrontend({
        page: pageParam,
        pageSize: PAGE_SIZE,
        search: debouncedSearch || undefined,
        sortBy,
        sortOrder,
      })
    },
    getNextPageParam: (lastPage: PaginatedEntityResponse<SupplierForFrontend>) => {
      if (lastPage.page < lastPage.total_pages) {
        return lastPage.page + 1
      }
      return undefined
    },
    initialPageParam: 1,
    // Keep previous data while fetching new results (prevents flash)
    placeholderData: (previousData) => previousData,
  })

  // Flatten all pages into a single array
  const suppliers = useMemo(() => {
    return data?.pages.flatMap(page => page.items) ?? []
  }, [data])

  const totalCount = data?.pages[0]?.total ?? 0

  const handleCardClick = (supplierId: string) => {
    navigate({ to: '/lieferanten/$supplierId', params: { supplierId } })
  }

  // Helper: Gesamtdokumente pro Lieferant berechnen
  const getTotalDocs = (supplier: SupplierForFrontend): number => {
    return Object.values(supplier.folderStats || {}).reduce(
      (sum, stats) => sum + (stats?.totalDocs || 0),
      0
    )
  }

  // Helper: Offene Rechnungen pro Lieferant berechnen
  const getOpenInvoices = (supplier: SupplierForFrontend): number => {
    return Object.values(supplier.folderStats || {}).reduce(
      (sum, stats) => sum + (stats?.openInvoices || 0),
      0
    )
  }

  // Check if this is the very first load (no data yet)
  const isInitialLoading = isLoading && !data

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Package className="w-8 h-8 text-blue-500" />
          Lieferanten
        </h1>
        <p className="text-muted-foreground mt-2">
          Wähle einen Lieferanten um die Dokumentenablage zu öffnen
        </p>
      </div>

      {/* Search + Sorting Controls */}
      <div className="flex flex-wrap gap-4 items-center">
        <SearchInput value={searchQuery} onChange={handleSearchChange} />

        {/* Sortierung */}
        <div className="flex items-center gap-2">
          <Select value={sortBy} onValueChange={(value) => setSortBy(value as SupplierSortField)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Sortieren nach" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="last_activity">Letzte Aktivität</SelectItem>
            </SelectContent>
          </Select>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
            aria-label={sortOrder === 'asc' ? 'Absteigend sortieren' : 'Aufsteigend sortieren'}
            title={sortOrder === 'asc' ? 'Aufsteigend (A→Z)' : 'Absteigend (Z→A)'}
          >
            {sortOrder === 'asc' ? (
              <ArrowUpNarrowWide className="w-5 h-5" />
            ) : (
              <ArrowDownWideNarrow className="w-5 h-5" />
            )}
          </Button>
        </div>
      </div>

      {/* Stats with loading indicator */}
      <div className="flex gap-4 items-center">
        <Badge variant="outline" className="text-sm py-1 px-3">
          {suppliers.length} von {totalCount.toLocaleString('de-DE')} Lieferanten
        </Badge>
        {isFetching && !isFetchingNextPage && (
          <div className="flex items-center gap-2 text-muted-foreground text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Suche...</span>
          </div>
        )}
      </div>

      {/* Error State */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="p-6 flex items-center gap-4">
            <AlertCircle className="w-8 h-8 text-destructive" />
            <div>
              <h3 className="font-semibold">Fehler beim Laden der Lieferanten</h3>
              <p className="text-sm text-muted-foreground">
                {error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten'}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Initial Loading State */}
      {isInitialLoading && (
        <div className="flex items-center justify-center min-h-[300px]">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            <p className="text-muted-foreground">Lade Lieferanten...</p>
          </div>
        </div>
      )}

      {/* Empty State */}
      {suppliers.length === 0 && !isLoading && !error && (
        <Card>
          <CardContent className="p-8 flex flex-col items-center justify-center text-center">
            <Package className="w-12 h-12 text-muted-foreground mb-4" />
            <h3 className="font-semibold text-lg">
              {debouncedSearch ? 'Keine Lieferanten gefunden' : 'Keine Lieferanten vorhanden'}
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              {debouncedSearch
                ? `Keine Ergebnisse für "${debouncedSearch}"`
                : 'Importiere Lieferanten über die Lexware-Schnittstelle'}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Supplier Cards */}
      {suppliers.length > 0 && !isInitialLoading && (
        <div className="space-y-4">
          {suppliers.map((supplier) => {
            const totalDocs = getTotalDocs(supplier)
            const openCount = getOpenInvoices(supplier)
            const folderCount = supplier.companyPresence?.length || 0

            return (
              <Card
                key={supplier.id}
                className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:border-l-4 hover:border-l-blue-500 hover:scale-[1.01] group"
                onClick={() => handleCardClick(supplier.id)}
              >
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    {/* Left: Folder Icon + Name */}
                    <div className="flex items-center gap-5">
                      <div className="p-3 rounded-xl bg-blue-50 dark:bg-blue-950/30 group-hover:bg-blue-100 dark:group-hover:bg-blue-950/50 group-hover:scale-110 transition-all">
                        <FolderOpen className="w-8 h-8 text-blue-500" />
                      </div>
                      <div>
                        <h3 className="font-bold text-xl group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                          {supplier.displayName}
                        </h3>
                        {supplier.fullName !== supplier.displayName && (
                          <p className="text-sm text-muted-foreground">{supplier.fullName}</p>
                        )}
                        <p className="text-sm text-muted-foreground mt-1">
                          {folderCount === 1 ? '1 Firma' : `${folderCount} Firmen`}
                        </p>
                      </div>
                    </div>

                    {/* Right: Stats + Arrow */}
                    <div className="flex items-center gap-8">
                      {/* Document Count */}
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <FileText className="w-5 h-5" />
                        <span className="font-medium">{totalDocs}</span>
                      </div>

                      {/* Open Invoices */}
                      {openCount > 0 ? (
                        <Badge variant="destructive" className="gap-1 py-1.5 px-3">
                          <AlertCircle className="w-3.5 h-3.5" />
                          {openCount} offen
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-muted-foreground py-1.5 px-3">
                          Keine offenen
                        </Badge>
                      )}

                      {/* Company Presence */}
                      <div className="hidden md:flex gap-1">
                        {supplier.companyPresence?.map((company) => (
                          <Badge key={company} variant="outline" className="text-xs py-1 px-2">
                            {company === 'messer' ? 'Messer' : 'Folie'}
                          </Badge>
                        ))}
                      </div>

                      {/* Status */}
                      {supplier.isActive ? (
                        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800 py-1.5 px-3">
                          Aktiv
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-gray-50 text-gray-500 border-gray-200 dark:bg-gray-900 dark:text-gray-400 dark:border-gray-700 py-1.5 px-3">
                          Inaktiv
                        </Badge>
                      )}

                      {/* Arrow */}
                      <ChevronRight className="w-6 h-6 text-muted-foreground group-hover:text-blue-500 group-hover:translate-x-2 transition-all" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}

          {/* Load More Button */}
          {hasNextPage && (
            <div className="flex justify-center pt-4">
              <Button
                variant="outline"
                size="lg"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className="gap-2"
              >
                {isFetchingNextPage ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Lade weitere...
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-4 h-4" />
                    Mehr laden ({totalCount - suppliers.length} weitere)
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
