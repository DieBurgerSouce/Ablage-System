import { useParams, Link } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, Upload, Filter, SortAsc, Eye, Download, MoreHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { CUSTOMER_CATEGORIES, SUPPLIER_CATEGORIES } from '../types'
import {
  getCustomerById,
  getCustomerFolder,
  getSupplierById,
  getSupplierFolder,
} from '../mockData'

interface CategoryDocumentListProps {
  entityType: 'customer' | 'supplier'
}

// Mock documents for demonstration
const MOCK_DOCUMENTS = [
  {
    id: 'doc-1',
    filename: 'RG-2024-00123.pdf',
    documentNumber: 'RG-2024-00123',
    documentType: 'invoice',
    date: '2024-12-15',
    amount: 1234.56,
    status: 'processed',
    createdAt: '2024-12-15T10:30:00',
  },
  {
    id: 'doc-2',
    filename: 'RG-2024-00124.pdf',
    documentNumber: 'RG-2024-00124',
    documentType: 'invoice',
    date: '2024-12-18',
    amount: 567.89,
    status: 'pending',
    createdAt: '2024-12-18T14:22:00',
  },
  {
    id: 'doc-3',
    filename: 'RG-2024-00125.pdf',
    documentNumber: 'RG-2024-00125',
    documentType: 'invoice',
    date: '2024-12-20',
    amount: 2345.0,
    status: 'processed',
    createdAt: '2024-12-20T09:15:00',
  },
  {
    id: 'doc-4',
    filename: 'RG-2024-00126.pdf',
    documentNumber: 'RG-2024-00126',
    documentType: 'invoice',
    date: '2024-12-22',
    amount: 789.0,
    status: 'review',
    createdAt: '2024-12-22T16:45:00',
  },
]

export function CategoryDocumentList({ entityType }: CategoryDocumentListProps) {
  const params = useParams({ strict: false })
  const isCustomer = entityType === 'customer'

  const entityId = isCustomer ? params.customerId : params.supplierId
  const folderId = params.folderId
  const category = params.category

  const categories = isCustomer ? CUSTOMER_CATEGORIES : SUPPLIER_CATEGORIES
  const basePath = isCustomer ? '/kunden' : '/lieferanten'
  const colorClass = isCustomer ? 'text-amber-500' : 'text-blue-500'

  // Get entity and folder info
  const entity = isCustomer
    ? (entityId ? getCustomerById(entityId) : null)
    : (entityId ? getSupplierById(entityId) : null)

  const folder = isCustomer
    ? (entityId && folderId ? getCustomerFolder(entityId, folderId) : null)
    : (entityId && folderId ? getSupplierFolder(entityId, folderId) : null)

  const entityName = entity?.displayName || (isCustomer ? 'Kunde' : 'Lieferant')
  const folderName = folder?.name || 'Ordner'
  const categoryInfo = categories.find((c) => c.id === category)

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  }

  const formatAmount = (amount: number) => {
    return amount.toLocaleString('de-DE', {
      style: 'currency',
      currency: 'EUR',
    })
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'processed':
        return (
          <Badge className="bg-green-100 text-green-800 hover:bg-green-100">
            Verarbeitet
          </Badge>
        )
      case 'pending':
        return (
          <Badge variant="secondary">
            Ausstehend
          </Badge>
        )
      case 'review':
        return (
          <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">
            Zur Pruefung
          </Badge>
        )
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  // Build paths for breadcrumbs
  const folderPath = isCustomer
    ? '/kunden/$customerId/$folderId'
    : '/lieferanten/$supplierId/$folderId'
  const folderParams = isCustomer
    ? { customerId: entityId!, folderId: folderId! }
    : { supplierId: entityId!, folderId: folderId! }
  const entityPath = isCustomer
    ? '/kunden/$customerId'
    : '/lieferanten/$supplierId'
  const entityParams = isCustomer
    ? { customerId: entityId! }
    : { supplierId: entityId! }

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to={folderPath} params={folderParams}>
          <Button variant="ghost" size="icon" aria-label="Zurueck zur Ordner-Uebersicht">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to={basePath} className="hover:text-foreground transition-colors">
              {isCustomer ? 'Kunden' : 'Lieferanten'}
            </Link>
            <span>/</span>
            <Link to={entityPath} params={entityParams} className="hover:text-foreground transition-colors">
              {entityName}
            </Link>
            <span>/</span>
            <Link to={folderPath} params={folderParams} className="hover:text-foreground transition-colors">
              {folderName}
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <FolderOpen className={`w-8 h-8 ${colorClass}`} />
            {categoryInfo?.label}
            {categoryInfo?.shortCode && (
              <span className="text-lg text-muted-foreground">({categoryInfo.shortCode})</span>
            )}
          </h1>
        </div>
      </div>

      {/* Actions Bar */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="gap-2">
            <Filter className="w-4 h-4" />
            Filter
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <SortAsc className="w-4 h-4" />
            Sortieren
          </Button>
        </div>
        <div className="flex gap-2">
          <Badge variant="outline" className="py-1.5">
            {MOCK_DOCUMENTS.length} Dokumente
          </Badge>
          <Button className="gap-2">
            <Upload className="w-4 h-4" />
            Dokument hochladen
          </Button>
        </div>
      </div>

      {/* Document Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]"></TableHead>
                <TableHead>Dateiname</TableHead>
                <TableHead>Dokumentnummer</TableHead>
                <TableHead>Datum</TableHead>
                <TableHead className="text-right">Betrag</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right w-[100px]">Aktionen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_DOCUMENTS.map((doc) => (
                <TableRow key={doc.id} className="group">
                  <TableCell>
                    <FileText className="w-4 h-4 text-muted-foreground" />
                  </TableCell>
                  <TableCell className="font-medium">
                    <Link
                      to="/documents/$documentId"
                      params={{ documentId: doc.id }}
                      className="hover:underline hover:text-primary transition-colors"
                    >
                      {doc.filename}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {doc.documentNumber}
                  </TableCell>
                  <TableCell>{formatDate(doc.date)}</TableCell>
                  <TableCell className="text-right font-mono">
                    {formatAmount(doc.amount)}
                  </TableCell>
                  <TableCell>
                    {getStatusBadge(doc.status)}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 transition-opacity">
                          <MoreHorizontal className="w-4 h-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem className="gap-2">
                          <Eye className="w-4 h-4" />
                          Anzeigen
                        </DropdownMenuItem>
                        <DropdownMenuItem className="gap-2">
                          <Download className="w-4 h-4" />
                          Herunterladen
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Empty State */}
      {MOCK_DOCUMENTS.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <FolderOpen className="w-16 h-16 mx-auto mb-4 opacity-30" />
          <p className="text-lg font-medium">Keine Dokumente vorhanden</p>
          <p className="text-sm mt-2">
            Laden Sie Dokumente in diese Kategorie hoch
          </p>
          <Button className="mt-4 gap-2">
            <Upload className="w-4 h-4" />
            Erstes Dokument hochladen
          </Button>
        </div>
      )}
    </div>
  )
}
