/**
 * ArchiveManagement Component
 *
 * Verwaltung archivierter Dokumente mit Integritaetspruefung.
 */

import { useState } from 'react'
import { format, formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import {
  Archive,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Search,
  RefreshCw,
  Shield,
  FileText,
  Calendar,
  Filter,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  useArchivedDocuments,
  useArchiveStatistics,
  useExpiringArchives,
  useVerifyDocument,
  useVerifyAllArchives,
} from '../hooks/use-gobd'
import type { RetentionCategory } from '../types'

const CATEGORY_LABELS: Record<RetentionCategory, string> = {
  invoice: 'Rechnung',
  contract: 'Vertrag',
  correspondence: 'Korrespondenz',
  tax_document: 'Steuerdokument',
  bank_statement: 'Kontoauszug',
  receipt: 'Beleg',
  other: 'Sonstige',
}

export function ArchiveManagement() {
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [page, setPage] = useState(1)

  const { data: archives, isLoading: archivesLoading } = useArchivedDocuments({
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
    page,
    page_size: 20,
  })
  const { data: statistics } = useArchiveStatistics()
  const { data: expiringArchives } = useExpiringArchives(90)
  const verifyDocument = useVerifyDocument()
  const verifyAll = useVerifyAllArchives()

  const formatDate = (dateString: string) => {
    return format(new Date(dateString), 'dd.MM.yyyy', { locale: de })
  }

  const formatRelativeDate = (dateString: string) => {
    return formatDistanceToNow(new Date(dateString), { addSuffix: true, locale: de })
  }

  return (
    <div className="space-y-6">
      {/* Statistik-Karten */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Archiviert</CardTitle>
            <Archive className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{statistics?.total_archived ?? 0}</div>
            <p className="text-xs text-muted-foreground">Dokumente insgesamt</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ablaufend</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{statistics?.expiring_soon ?? 0}</div>
            <p className="text-xs text-muted-foreground">In den naechsten 90 Tagen</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Unverifiziert</CardTitle>
            <Shield className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{statistics?.unverified ?? 0}</div>
            <p className="text-xs text-muted-foreground">Pruefung ausstehend</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Speicher</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statistics?.storage_size_bytes
                ? `${(statistics.storage_size_bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
                : '0 GB'}
            </div>
            <p className="text-xs text-muted-foreground">Archiv-Groesse</p>
          </CardContent>
        </Card>
      </div>

      {/* Ablaufende Archive Warnung */}
      {expiringArchives && expiringArchives.length > 0 && (
        <Card className="border-yellow-500/50 bg-yellow-500/10">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-yellow-600">
              <AlertTriangle className="h-5 w-5" />
              Aufbewahrungsfristen laufen ab
            </CardTitle>
            <CardDescription>
              {expiringArchives.length} Dokument(e) erreichen in den naechsten 90 Tagen das Ende
              ihrer Aufbewahrungsfrist.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {expiringArchives.slice(0, 5).map((archive) => (
                <div
                  key={archive.id}
                  className="flex items-center justify-between rounded-md bg-background/50 p-2"
                >
                  <span className="text-sm">{archive.document_title}</span>
                  <Badge variant="outline" className="text-yellow-600">
                    {archive.days_until_expiry} Tage
                  </Badge>
                </div>
              ))}
              {expiringArchives.length > 5 && (
                <p className="text-sm text-muted-foreground">
                  ... und {expiringArchives.length - 5} weitere
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Archiv-Tabelle */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Archivierte Dokumente</CardTitle>
              <CardDescription>
                GoBD-konform archivierte Dokumente mit SHA-256 Signatur
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={() => verifyAll.mutate()}
              disabled={verifyAll.isPending}
            >
              <RefreshCw
                className={`mr-2 h-4 w-4 ${verifyAll.isPending ? 'animate-spin' : ''}`}
              />
              Alle verifizieren
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Filter */}
          <div className="mb-4 flex gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Dokumente suchen..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="w-[200px]">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Kategorie" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Kategorien</SelectItem>
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Tabelle */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dokument</TableHead>
                  <TableHead>Kategorie</TableHead>
                  <TableHead>Archiviert</TableHead>
                  <TableHead>Ablauf</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {archivesLoading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8">
                      <RefreshCw className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                ) : archives?.items && archives.items.length > 0 ? (
                  archives.items.map((archive) => (
                    <TableRow key={archive.id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <span className="truncate max-w-[200px]">{archive.document_id}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {CATEGORY_LABELS[archive.retention_category as RetentionCategory] ||
                            archive.retention_category}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 text-sm text-muted-foreground">
                          <Calendar className="h-3 w-3" />
                          {formatDate(archive.archived_at)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">{formatDate(archive.retention_expires_at)}</span>
                      </TableCell>
                      <TableCell>
                        {archive.is_verified ? (
                          <Badge
                            variant="outline"
                            className="border-green-500/50 bg-green-500/10 text-green-600"
                          >
                            <CheckCircle2 className="mr-1 h-3 w-3" />
                            Verifiziert
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="border-orange-500/50 bg-orange-500/10 text-orange-600"
                          >
                            <AlertTriangle className="mr-1 h-3 w-3" />
                            Ausstehend
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => verifyDocument.mutate(archive.document_id)}
                          disabled={verifyDocument.isPending}
                        >
                          <Shield className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      Keine archivierten Dokumente gefunden
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          {archives && archives.total > 20 && (
            <div className="mt-4 flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Seite {page} von {Math.ceil(archives.total / 20)}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  Zurueck
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= Math.ceil(archives.total / 20)}
                >
                  Weiter
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
