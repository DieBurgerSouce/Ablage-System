import { useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Package, FolderOpen, ChevronRight, FileText, AlertCircle, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { fetchSuppliersForFrontend, type SupplierForFrontend } from '../api/ablage-api'

/**
 * LieferantenPage - Zeigt alle Lieferanten als klickbare Ordner-Cards
 *
 * Klick auf einen Lieferanten navigiert zur Ordner-Auswahl (Spargelmesser/Folie)
 * Display-Format: Nur Matchcode (KEINE Nummer - weil Nummern chaotisch)
 *
 * Route: /lieferanten
 */
export function LieferantenPage() {
  const navigate = useNavigate()

  const { data: suppliers = [], isLoading, error } = useQuery({
    queryKey: ['suppliers'],
    queryFn: fetchSuppliersForFrontend,
  })

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

  const totalDocuments = suppliers.reduce((sum, s) => sum + getTotalDocs(s), 0)

  // Loading State
  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          <p className="text-muted-foreground">Lade Lieferanten...</p>
        </div>
      </div>
    )
  }

  // Error State
  if (error) {
    return (
      <div className="p-8">
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
      </div>
    )
  }

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

      {/* Stats */}
      <div className="flex gap-4">
        <Badge variant="outline" className="text-sm py-1 px-3">
          {suppliers.length} Lieferanten
        </Badge>
        <Badge variant="outline" className="text-sm py-1 px-3">
          {totalDocuments.toLocaleString('de-DE')} Dokumente gesamt
        </Badge>
      </div>

      {/* Empty State */}
      {suppliers.length === 0 && (
        <Card>
          <CardContent className="p-8 flex flex-col items-center justify-center text-center">
            <Package className="w-12 h-12 text-muted-foreground mb-4" />
            <h3 className="font-semibold text-lg">Keine Lieferanten vorhanden</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Importiere Lieferanten über die Lexware-Schnittstelle
            </p>
          </CardContent>
        </Card>
      )}

      {/* Supplier Cards */}
      {suppliers.length > 0 && (
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
                          {folderCount} Ablage-Ordner
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
        </div>
      )}
    </div>
  )
}
