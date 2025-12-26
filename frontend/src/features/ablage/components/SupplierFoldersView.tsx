import { useParams, Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, ChevronRight, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { getSupplierById, getSupplierTotalDocuments, getSupplierOpenInvoices } from '../mockData'

/**
 * SupplierFoldersView - Zeigt die 2 Ablage-Ordner eines Lieferanten:
 * - Spargelmesser1
 * - Folie
 *
 * Route: /lieferanten/$supplierId
 */
export function SupplierFoldersView() {
  const { supplierId } = useParams({ strict: false })
  const navigate = useNavigate()

  const supplier = supplierId ? getSupplierById(supplierId) : null

  if (!supplier) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <FolderOpen className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
          <h2 className="text-xl font-semibold mb-2">Lieferant nicht gefunden</h2>
          <p className="text-muted-foreground mb-4">
            Der gesuchte Lieferant existiert nicht.
          </p>
          <Link to="/lieferanten">
            <Button variant="outline">Zurueck zur Lieferantenliste</Button>
          </Link>
        </div>
      </div>
    )
  }

  const totalDocs = getSupplierTotalDocuments(supplier)
  const totalOpen = getSupplierOpenInvoices(supplier)

  const handleFolderClick = (folderId: string) => {
    navigate({
      to: '/lieferanten/$supplierId/$folderId',
      params: { supplierId: supplierId!, folderId },
    })
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to="/lieferanten">
          <Button variant="ghost" size="icon" aria-label="Zurueck zur Lieferantenliste">
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
          <h1 className="text-3xl font-bold tracking-tight">{supplier.displayName}</h1>
          {supplier.name !== supplier.displayName && (
            <p className="text-muted-foreground">{supplier.name}</p>
          )}
        </div>
      </div>

      {/* Supplier Stats */}
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
        <Badge variant="outline" className="text-sm py-1.5 px-3">
          Letzte Aktivitaet: {formatDate(supplier.lastActivityDate)}
        </Badge>
        {supplier.isActive ? (
          <Badge className="bg-green-100 text-green-800 hover:bg-green-100 text-sm py-1.5 px-3">
            Aktiv
          </Badge>
        ) : (
          <Badge variant="secondary" className="text-sm py-1.5 px-3">
            Inaktiv
          </Badge>
        )}
      </div>

      {/* Folder Selection */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Waehle einen Ablage-Ordner:</h2>
        <div className="space-y-4">
          {supplier.folders.map((folder) => {
            const openCount = folder.documentCounts.offene_rechnungen ?? 0
            return (
              <Card
                key={folder.id}
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
                          {folder.totalDocuments} Dokumente in diesem Ordner
                        </p>
                      </div>
                    </div>

                    {/* Right: Stats + Arrow */}
                    <div className="flex items-center gap-8">
                      {/* Document Count */}
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <FileText className="w-5 h-5" />
                        <span className="font-medium">{folder.totalDocuments}</span>
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
                        {formatDate(folder.lastDocumentDate)}
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
