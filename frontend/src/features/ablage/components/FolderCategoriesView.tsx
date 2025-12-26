import { useParams, Link } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CUSTOMER_CATEGORIES, SUPPLIER_CATEGORIES } from '../types'
import {
  getCustomerById,
  getCustomerFolder,
  getSupplierById,
  getSupplierFolder,
} from '../mockData'

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

  // Get entity and folder data
  const entity = isCustomer
    ? (entityId ? getCustomerById(entityId) : null)
    : (entityId ? getSupplierById(entityId) : null)

  const folder = isCustomer
    ? (entityId && folderId ? getCustomerFolder(entityId, folderId) : null)
    : (entityId && folderId ? getSupplierFolder(entityId, folderId) : null)

  const entityName = entity?.displayName || (isCustomer ? 'Unbekannter Kunde' : 'Unbekannter Lieferant')
  const folderName = folder?.name || 'Unbekannter Ordner'

  const formatDate = (dateStr?: string) => {
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

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to={parentPath} params={parentParams}>
          <Button variant="ghost" size="icon" aria-label="Zurueck zum Kunden/Lieferanten">
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
          {folder?.totalDocuments ?? 0} Dokumente
        </Badge>
        <Badge variant="outline" className="text-sm py-1.5 px-3">
          Letzte Aktivitaet: {formatDate(folder?.lastDocumentDate)}
        </Badge>
      </div>

      {/* Category Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {categories.map((category) => {
          const count = folder?.documentCounts[category.id] ?? 0
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
