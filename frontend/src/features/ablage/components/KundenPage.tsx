import { useState, useMemo, useEffect, useCallback, memo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Users, FolderOpen, ChevronRight, FileText, AlertCircle, Loader2, Search, ChevronDown, ArrowUpNarrowWide, ArrowDownWideNarrow } from 'lucide-react'
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
import { fetchCustomersForFrontend, type CustomerForFrontend, type PaginatedEntityResponse, type CustomerSortField } from '../api/ablage-api'

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
        placeholder="Suche nach Kundennummer oder Name..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pl-10"
      />
    </div>
  )
})

/**
 * KundenPage - Zeigt Kunden als klickbare Ordner-Cards mit Suche und Pagination
 *
 * Klick auf einen Kunden navigiert zur Ordner-Auswahl (Spargelmesser/Folie)
 * Display-Format: Kundennummer_Matchcode (z.B. "12345_Mueller")
 *
 * Route: /kunden
 */
export function KundenPage() {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sortBy, setSortBy] = useState<CustomerSortField>('name')
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
    queryKey: ['customers', debouncedSearch, sortBy, sortOrder],
    queryFn: async ({ pageParam = 1 }) => {
      return fetchCustomersForFrontend({
        page: pageParam,
        pageSize: PAGE_SIZE,
        search: debouncedSearch || undefined,
        sortBy,
        sortOrder,
      })
    },
    getNextPageParam: (lastPage: PaginatedEntityResponse<CustomerForFrontend>) => {
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
  const customers = useMemo(() => {
    return data?.pages.flatMap(page => page.items) ?? []
  }, [data])

  const totalCount = data?.pages[0]?.total ?? 0

  const handleCardClick = (customerId: string) => {
    navigate({ to: '/kunden/$customerId', params: { customerId } })
  }

  // Helper: Gesamtdokumente pro Kunde berechnen
  const getTotalDocs = (customer: CustomerForFrontend): number => {
    return Object.values(customer.folderStats || {}).reduce(
      (sum, stats) => sum + (stats?.totalDocs || 0),
      0
    )
  }

  // Helper: Offene Rechnungen pro Kunde berechnen
  const getOpenInvoices = (customer: CustomerForFrontend): number => {
    return Object.values(customer.folderStats || {}).reduce(
      (sum, stats) => sum + (stats?.openInvoices || 0),
      0
    )
  }

  // Helper: Prüft ob fullName ein echter Firmenname ist (nicht nur der Matchcode)
  // displayName = "12345_Mueller", fullName = "Hofgemeinschaft GbR" -> true (zeigen)
  // displayName = "12345_Mueller", fullName = "Mueller" -> false (redundant, nicht zeigen)
  // displayName = "12345_Mueller", fullName = "" -> false (leer, nicht zeigen)
  const isRealCompanyName = (fullName: string, displayName: string): boolean => {
    if (!fullName || fullName.trim() === '') return false
    // Matchcode extrahieren (Teil nach dem Underscore in displayName)
    const matchcode = displayName.includes('_')
      ? displayName.split('_').slice(1).join('_')
      : displayName
    // Nur anzeigen wenn fullName unterschiedlich zum Matchcode ist
    return fullName.trim().toLowerCase() !== matchcode.trim().toLowerCase()
  }

  // Check if this is the very first load (no data yet)
  const isInitialLoading = isLoading && !data

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Users className="w-8 h-8 text-amber-500" />
          Kunden
        </h1>
        <p className="text-muted-foreground mt-2">
          Wähle einen Kunden um die Dokumentenablage zu öffnen
        </p>
      </div>

      {/* Search + Sorting Controls */}
      <div className="flex flex-wrap gap-4 items-center">
        <SearchInput value={searchQuery} onChange={handleSearchChange} />

        {/* Sortierung */}
        <div className="flex items-center gap-2">
          <Select value={sortBy} onValueChange={(value) => setSortBy(value as CustomerSortField)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Sortieren nach" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="customer_number">Kundennummer</SelectItem>
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
          {customers.length} von {totalCount.toLocaleString('de-DE')} Kunden
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
              <h3 className="font-semibold">Fehler beim Laden der Kunden</h3>
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
            <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
            <p className="text-muted-foreground">Lade Kunden...</p>
          </div>
        </div>
      )}

      {/* Empty State */}
      {customers.length === 0 && !isLoading && !error && (
        <Card>
          <CardContent className="p-8 flex flex-col items-center justify-center text-center">
            <Users className="w-12 h-12 text-muted-foreground mb-4" />
            <h3 className="font-semibold text-lg">
              {debouncedSearch ? 'Keine Kunden gefunden' : 'Keine Kunden vorhanden'}
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              {debouncedSearch
                ? `Keine Ergebnisse für "${debouncedSearch}"`
                : 'Importiere Kunden über die Lexware-Schnittstelle'}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Customer Cards */}
      {customers.length > 0 && !isInitialLoading && (
        <div className="space-y-4">
          {customers.map((customer) => {
            const totalDocs = getTotalDocs(customer)
            const openCount = getOpenInvoices(customer)
            const folderCount = customer.companyPresence?.length || 0

            return (
              <Card
                key={customer.id}
                data-testid="customer-card"
                className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:border-l-4 hover:border-l-amber-500 hover:scale-[1.01] group"
                onClick={() => handleCardClick(customer.id)}
              >
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    {/* Left: Folder Icon + Name */}
                    <div className="flex items-center gap-5">
                      <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 group-hover:bg-amber-100 dark:group-hover:bg-amber-950/50 group-hover:scale-110 transition-all">
                        <FolderOpen className="w-8 h-8 text-amber-500" />
                      </div>
                      <div>
                        <h3 className="font-bold text-xl group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                          {customer.displayName}
                        </h3>
                        {isRealCompanyName(customer.fullName, customer.displayName) && (
                          <p className="text-sm text-muted-foreground">{customer.fullName}</p>
                        )}
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
                        {customer.companyPresence?.map((company) => (
                          <Badge key={company} variant="outline" className="text-xs py-1 px-2">
                            {company === 'messer' ? 'Messer' : 'Folie'}
                          </Badge>
                        ))}
                      </div>

                      {/* Status */}
                      {customer.isActive ? (
                        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800 py-1.5 px-3">
                          Aktiv
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="bg-gray-50 text-gray-500 border-gray-200 dark:bg-gray-900 dark:text-gray-400 dark:border-gray-700 py-1.5 px-3">
                          Inaktiv
                        </Badge>
                      )}

                      {/* Arrow */}
                      <ChevronRight className="w-6 h-6 text-muted-foreground group-hover:text-amber-500 group-hover:translate-x-2 transition-all" />
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
                    Mehr laden ({totalCount - customers.length} weitere)
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
