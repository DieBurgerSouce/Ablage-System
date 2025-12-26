import { useNavigate } from '@tanstack/react-router'
import { Users, FolderOpen, ChevronRight, FileText, AlertCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { getAllCustomers, getCustomerTotalDocuments, getCustomerOpenInvoices } from '../mockData'

/**
 * KundenPage - Zeigt alle Kunden als klickbare Ordner-Cards
 *
 * Klick auf einen Kunden navigiert zur Ordner-Auswahl (Spargelmesser/Folie)
 *
 * Route: /kunden
 */
export function KundenPage() {
  const navigate = useNavigate()
  const customers = getAllCustomers()

  const handleCardClick = (customerId: string) => {
    navigate({ to: '/kunden/$customerId', params: { customerId } })
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  }

  const totalDocuments = customers.reduce((sum, c) => sum + getCustomerTotalDocuments(c), 0)

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Users className="w-8 h-8 text-amber-500" />
          Kunden
        </h1>
        <p className="text-muted-foreground mt-2">
          Waehle einen Kunden um die Dokumentenablage zu oeffnen
        </p>
      </div>

      {/* Stats */}
      <div className="flex gap-4">
        <Badge variant="outline" className="text-sm py-1 px-3">
          {customers.length} Kunden
        </Badge>
        <Badge variant="outline" className="text-sm py-1 px-3">
          {totalDocuments.toLocaleString('de-DE')} Dokumente gesamt
        </Badge>
      </div>

      {/* Customer Cards */}
      <div className="space-y-4">
        {customers.map((customer) => {
          const totalDocs = getCustomerTotalDocuments(customer)
          const openCount = getCustomerOpenInvoices(customer)

          return (
            <Card
              key={customer.id}
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
                      {customer.name !== customer.displayName && (
                        <p className="text-sm text-muted-foreground">{customer.name}</p>
                      )}
                      <p className="text-sm text-muted-foreground mt-1">
                        {customer.folders.length} Ablage-Ordner
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

                    {/* Last Activity */}
                    <span className="text-sm text-muted-foreground hidden md:block min-w-[90px]">
                      {formatDate(customer.lastActivityDate)}
                    </span>

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
      </div>
    </div>
  )
}
