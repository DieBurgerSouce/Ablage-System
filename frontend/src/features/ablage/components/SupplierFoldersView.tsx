import { useEffect } from 'react'
import { useParams, Link, useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FolderOpen, FileText, ChevronRight, AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { fetchEntityFolders, type EntityFolder } from '../api/ablage-api'

/**
 * SupplierFoldersView - Zeigt die Ablage-Ordner eines Lieferanten:
 * - Spargelmesser
 * - Folie
 *
 * Route: /lieferanten/$supplierId
 */
export function SupplierFoldersView() {
  const { supplierId } = useParams({ strict: false })
  const navigate = useNavigate()

  const { data: folders = [], isLoading, error } = useQuery({
    queryKey: ['entityFolders', supplierId],
    queryFn: () => fetchEntityFolders(supplierId!),
    enabled: !!supplierId,
  })

  const handleFolderClick = (folderId: string) => {
    navigate({
      to: '/lieferanten/$supplierId/$folderId',
      params: { supplierId: supplierId!, folderId },
    })
  }

  // Auto-Navigation: Wenn nur eine Firma vorhanden ist, direkt dorthin navigieren
  useEffect(() => {
    if (!isLoading && !error && folders.length === 1) {
      navigate({
        to: '/lieferanten/$supplierId/$folderId',
        params: { supplierId: supplierId!, folderId: folders[0].id },
        replace: true, // Ersetzt den History-Eintrag, damit Zurück zur Lieferantenliste führt
      })
    }
  }, [isLoading, error, folders, supplierId, navigate])

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  }

  // Helper: Berechne Gesamtdokumente über alle Ordner
  const getTotalDocs = (folder: EntityFolder): number => {
    return Object.values(folder.documentCounts || {}).reduce((sum, count) => sum + count, 0)
  }

  // Loading State (auch während Auto-Navigation bei nur einer Firma)
  if (isLoading || (!error && folders.length === 1)) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          <p className="text-muted-foreground">
            {folders.length === 1 ? 'Öffne Firma...' : 'Lade Ordner...'}
          </p>
        </div>
      </div>
    )
  }

  // Error State
  if (error) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-4 mb-6">
          <Link to="/lieferanten">
            <Button variant="ghost" size="icon" aria-label="Zurück zur Lieferantenliste">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Fehler</h1>
        </div>
        <Card className="border-destructive">
          <CardContent className="p-6 flex items-center gap-4">
            <AlertCircle className="w-8 h-8 text-destructive" />
            <div>
              <h3 className="font-semibold">Fehler beim Laden der Ordner</h3>
              <p className="text-sm text-muted-foreground">
                {error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // No folders found
  if (folders.length === 0) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-4 mb-6">
          <Link to="/lieferanten">
            <Button variant="ghost" size="icon" aria-label="Zurück zur Lieferantenliste">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
        </div>
        <div className="text-center py-12">
          <FolderOpen className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
          <h2 className="text-xl font-semibold mb-2">Keine Ordner gefunden</h2>
          <p className="text-muted-foreground mb-4">
            Dieser Lieferant hat noch keine Ablage-Ordner.
          </p>
          <Link to="/lieferanten">
            <Button variant="outline">Zurück zur Lieferantenliste</Button>
          </Link>
        </div>
      </div>
    )
  }

  // Calculate totals
  const totalDocs = folders.reduce((sum, f) => sum + getTotalDocs(f), 0)
  const totalOpen = folders.reduce((sum, f) => sum + (f.openInvoices || 0), 0)

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to="/lieferanten">
          <Button variant="ghost" size="icon" aria-label="Zurück zur Lieferantenliste">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to="/lieferanten" className="hover:text-foreground transition-colors">
              Lieferanten
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Lieferant</h1>
          <p className="text-muted-foreground">Wähle eine der Firmen</p>
        </div>
      </div>

      {/* Stats */}
      <div className="flex flex-wrap gap-4">
        <Badge variant="secondary" className="text-sm py-1.5 px-3">
          <FileText className="w-4 h-4 mr-2" />
          {totalDocs} Dokumente gesamt
        </Badge>
        {totalOpen > 0 && (
          <Badge variant="destructive" className="text-sm py-1.5 px-3">
            <AlertCircle className="w-4 h-4 mr-2" />
            {totalOpen} offene Rechnungen
          </Badge>
        )}
      </div>

      {/* Folder Selection */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Wähle eine der Firmen:</h2>
        <div className="space-y-4">
          {folders.map((folder) => {
            const folderDocs = getTotalDocs(folder)
            const openCount = folder.openInvoices || 0

            return (
              <Card
                key={folder.id}
                data-testid="folder-card"
                className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:border-l-4 hover:border-l-blue-500 hover:scale-[1.01] group"
                onClick={() => handleFolderClick(folder.id)}
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
                          {folder.name}
                        </h3>
                        <p className="text-sm text-muted-foreground mt-1">
                          {folderDocs} Dokumente in diesem Ordner
                        </p>
                      </div>
                    </div>

                    {/* Right: Stats + Arrow */}
                    <div className="flex items-center gap-8">
                      {/* Document Count */}
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <FileText className="w-5 h-5" />
                        <span className="font-medium">{folderDocs}</span>
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

                      {/* Last Activity */}
                      <span className="text-sm text-muted-foreground hidden md:block min-w-[90px]">
                        {formatDate(folder.lastActivity)}
                      </span>

                      {/* Arrow */}
                      <ChevronRight className="w-6 h-6 text-muted-foreground group-hover:text-blue-500 group-hover:translate-x-2 transition-all" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
