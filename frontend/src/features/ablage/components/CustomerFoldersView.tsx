import { useParams, Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, ChevronRight, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { getCustomerById, getCustomerTotalDocuments, getCustomerOpenInvoices } from '../mockData'

/**
 * CustomerFoldersView - Zeigt die 2 Ablage-Ordner eines Kunden:
 * - Spargelmesser
 * - Folie
 *
 * Route: /kunden/$customerId
 */
export function CustomerFoldersView() {
  const { customerId } = useParams({ strict: false })
  const navigate = useNavigate()

  const customer = customerId ? getCustomerById(customerId) : null

  if (!customer) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <FolderOpen className="w-16 h-16 mx-auto mb-4 text-muted-foreground opacity-50" />
          <h2 className="text-xl font-semibold mb-2">Kunde nicht gefunden</h2>
          <p className="text-muted-foreground mb-4">
            Der gesuchte Kunde existiert nicht.
          </p>
          <Link to="/kunden">
            <Button variant="outline">Zurueck zur Kundenliste</Button>
          </Link>
        </div>
      </div>
    )
  }

  const totalDocs = getCustomerTotalDocuments(customer)
  const totalOpen = getCustomerOpenInvoices(customer)

  const handleFolderClick = (folderId: string) => {
    navigate({
      to: '/kunden/$customerId/$folderId',
      params: { customerId: customerId!, folderId },
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
        <Link to="/kunden">
          <Button variant="ghost" size="icon" aria-label="Zurueck zur Kundenliste">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to="/kunden" className="hover:text-foreground transition-colors">
              Kunden
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{customer.displayName}</h1>
          {customer.name !== customer.displayName && (
            <p className="text-muted-foreground">{customer.name}</p>
          )}
        </div>
      </div>

      {/* Customer Stats */}
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
          Letzte Aktivitaet: {formatDate(customer.lastActivityDate)}
        </Badge>
        {customer.isActive ? (
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
          {customer.folders.map((folder) => {
            const openCount = folder.documentCounts.offene_rechnungen ?? 0
            return (
              <Card
                key={folder.id}
                className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:border-l-4 hover:border-l-amber-500 hover:scale-[1.01] group"
                onClick={() => handleFolderClick(folder.id)}
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
                      <ChevronRight className="w-6 h-6 text-muted-foreground group-hover:text-amber-500 group-hover:translate-x-2 transition-all" />
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
