import { useParams, Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FolderOpen, FileText, Upload, Loader2, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CUSTOMER_CATEGORIES, SUPPLIER_CATEGORIES } from '../types'
import { fetchEntityFolders, fetchEntityName, type EntityFolder } from '../api/ablage-api'

interface FolderCategoriesViewProps {
  entityType: 'customer' | 'supplier'
}

/**
 * FolderCategoriesView - Zeigt die Dokument-Kategorien eines Ordners:
 * Anfragen, Angebote, Rechnungen, etc.
 *
 * Route: /kunden/$customerId/$folderId oder /lieferanten/$supplierId/$folderId
 */
export function FolderCategoriesView({ entityType }: FolderCategoriesViewProps) {
  const params = useParams({ strict: false })
  const isCustomer = entityType === 'customer'

  const entityId = isCustomer ? params.customerId : params.supplierId
  const folderId = params.folderId

  const categories = isCustomer ? CUSTOMER_CATEGORIES : SUPPLIER_CATEGORIES
  const basePath = isCustomer ? '/kunden' : '/lieferanten'
  const colorClass = isCustomer ? 'text-amber-500' : 'text-blue-500'
  const colorHoverClass = isCustomer ? 'hover:border-amber-500/50' : 'hover:border-blue-500/50'
  const bgColorClass = isCustomer ? 'bg-amber-50 dark:bg-amber-950/30' : 'bg-blue-50 dark:bg-blue-950/30'

  // Fetch entity name
  const { data: entityInfo, isLoading: isLoadingEntity, error: entityError } = useQuery({
    queryKey: ['entityInfo', entityId],
    queryFn: () => fetchEntityName(entityId!),
    enabled: !!entityId,
  })

  // Fetch folders for entity
  const { data: folders = [], isLoading: isLoadingFolders, error: foldersError } = useQuery({
    queryKey: ['entityFolders', entityId],
    queryFn: () => fetchEntityFolders(entityId!),
    enabled: !!entityId,
  })

  // Find the current folder from the list
  const folder = folders.find((f: EntityFolder) => f.id === folderId)

  const entityName = entityInfo?.name || (isCustomer ? 'Unbekannter Kunde' : 'Unbekannter Lieferant')
  const folderName = folder?.name || 'Unbekannter Ordner'

  // Helper: Berechne Gesamtdokumente im Ordner
  const getTotalDocs = (f: EntityFolder): number => {
    return Object.values(f.documentCounts || {}).reduce((sum, count) => sum + count, 0)
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  }

  const parentPath = isCustomer
    ? `/kunden/$customerId`
    : `/lieferanten/$supplierId`

  const parentParams = isCustomer
    ? { customerId: entityId! }
    : { supplierId: entityId! }

  const isLoading = isLoadingEntity || isLoadingFolders
  const error = entityError || foldersError

  // Loading State
  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className={`w-8 h-8 animate-spin ${colorClass}`} />
          <p className="text-muted-foreground">Lade Kategorien...</p>
        </div>
      </div>
    )
  }

  // Error State
  if (error) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-4 mb-6">
          <Link to={basePath}>
            <Button variant="ghost" size="icon" aria-label="Zurück">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Fehler</h1>
        </div>
        <Card className="border-destructive">
          <CardContent className="p-6 flex items-center gap-4">
            <AlertCircle className="w-8 h-8 text-destructive" />
            <div>
              <h3 className="font-semibold">Fehler beim Laden</h3>
              <p className="text-sm text-muted-foreground">
                {error instanceof Error ? error.message : 'Ein unbekannter Fehler ist aufgetreten'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Folder not found
  if (!folder) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-4 mb-6">
          <Link to={parentPath} params={parentParams}>
            <Button variant="ghost" size="icon" aria-label="Zurück">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
        </div>
        <div className="text-center py-12">
          <FolderOpen className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
          <h2 className="text-xl font-semibold mb-2">Ordner nicht gefunden</h2>
          <p className="text-muted-foreground mb-4">
            Der angeforderte Ordner existiert nicht.
          </p>
          <Link to={parentPath} params={parentParams}>
            <Button variant="outline">Zurück zur Ordnerauswahl</Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to={parentPath} params={parentParams}>
          <Button variant="ghost" size="icon" aria-label="Zurück zum Kunden/Lieferanten">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to={basePath} className="hover:text-foreground transition-colors">
              {isCustomer ? 'Kunden' : 'Lieferanten'}
            </Link>
            <span>/</span>
            <Link to={parentPath} params={parentParams} className="hover:text-foreground transition-colors">
              {entityName}
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <FolderOpen className={`w-8 h-8 ${colorClass}`} />
            {folderName}
          </h1>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="flex flex-wrap gap-4">
        <Badge variant="secondary" className="text-sm py-1.5 px-3">
          <FileText className="w-4 h-4 mr-2" />
          {getTotalDocs(folder)} Dokumente
        </Badge>
        {folder.openInvoices > 0 && (
          <Badge variant="destructive" className="text-sm py-1.5 px-3">
            <AlertCircle className="w-4 h-4 mr-2" />
            {folder.openInvoices} offene Rechnungen
          </Badge>
        )}
        <Badge variant="outline" className="text-sm py-1.5 px-3">
          Letzte Aktivitaet: {formatDate(folder.lastActivity)}
        </Badge>
      </div>

      {/* Category Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {categories.map((category) => {
          const count = folder.documentCounts[category.id] ?? 0
          const categoryPath = isCustomer
            ? `/kunden/$customerId/$folderId/$category`
            : `/lieferanten/$supplierId/$folderId/$category`
          const categoryParams = isCustomer
            ? { customerId: entityId!, folderId: folderId!, category: category.id }
            : { supplierId: entityId!, folderId: folderId!, category: category.id }

          return (
            <Link key={category.id} to={categoryPath} params={categoryParams}>
              <Card className={`${colorHoverClass} hover:shadow-md transition-all cursor-pointer h-full group`}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <div className={`p-1.5 rounded ${bgColorClass} group-hover:scale-110 transition-transform`}>
                      <FolderOpen className={`w-4 h-4 ${colorClass}`} />
                    </div>
                    <span className="truncate">{category.label}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    {category.shortCode && (
                      <span className="text-xs text-muted-foreground">({category.shortCode})</span>
                    )}
                    <Badge
                      variant={category.isOpenStatus && count > 0 ? 'destructive' : 'secondary'}
                      className="ml-auto"
                    >
                      {count}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            </Link>
          )
        })}
      </div>

      {/* Quick Upload */}
      <Card className="border-dashed">
        <CardContent className="flex items-center justify-center py-8">
          <Button variant="outline" className="gap-2">
            <Upload className="w-4 h-4" />
            Dokument zu {folderName} hochladen
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
