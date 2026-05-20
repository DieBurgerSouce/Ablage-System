/**
 * Integrations-Synchronisation (DATEV Write-back + Lexware Export)
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftRight,
  Download,
  Upload,
  Loader2,
  CheckCircle2,
  Clock,
  FileText,
  Users,
  Building2,
  CreditCard,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'

// Types
interface DatevWritebackBatch {
  id: string
  chart_of_accounts: 'SKR03' | 'SKR04'
  consultant_number: string
  client_number: string
  status: 'draft' | 'ready' | 'exported' | 'imported'
  records_count: number
  created_at: string
  exported_at: string | null
  import_confirmed_at: string | null
}

interface CreateDatevBatchRequest {
  chart_of_accounts: 'SKR03' | 'SKR04'
  consultant_number: string
  client_number: string
}

interface LexwareExportJob {
  id: string
  export_type: 'customers' | 'suppliers' | 'payment_status'
  status: 'pending' | 'running' | 'completed' | 'failed'
  records_count: number
  created_at: string
  completed_at: string | null
  file_path: string | null
}

const API_BASE = '/api/v1'

// DATEV API functions
async function getDatevBatches(): Promise<DatevWritebackBatch[]> {
  const res = await fetch(`${API_BASE}/admin/integration-sync/datev/writeback`)
  if (!res.ok) throw new Error('Fehler beim Laden der DATEV-Batches')
  return res.json()
}

async function createDatevBatch(request: CreateDatevBatchRequest): Promise<DatevWritebackBatch> {
  const res = await fetch(`${API_BASE}/admin/integration-sync/datev/writeback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error('Fehler beim Erstellen des Batches')
  return res.json()
}

async function downloadDatevBatch(batchId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/admin/integration-sync/datev/writeback/${batchId}/download`)
  if (!res.ok) throw new Error('Fehler beim Download')
  return res.blob()
}

async function confirmDatevImport(batchId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/admin/integration-sync/datev/writeback/${batchId}/confirm-import`,
    { method: 'POST' }
  )
  if (!res.ok) throw new Error('Fehler beim Bestätigen')
}

// Lexware API functions
async function getLexwareExports(): Promise<LexwareExportJob[]> {
  const res = await fetch(`${API_BASE}/admin/integration-sync/lexware/exports`)
  if (!res.ok) throw new Error('Fehler beim Laden der Exports')
  return res.json()
}

async function createLexwareExport(exportType: 'customers' | 'suppliers' | 'payment_status'): Promise<LexwareExportJob> {
  const res = await fetch(`${API_BASE}/admin/integration-sync/lexware/export/${exportType}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Fehler beim Starten des Exports')
  return res.json()
}

async function downloadLexwareExport(jobId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/admin/integration-sync/lexware/export/${jobId}/download`)
  if (!res.ok) throw new Error('Fehler beim Download')
  return res.blob()
}

export function IntegrationSyncPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('datev')
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)

  // DATEV form state
  const [chartOfAccounts, setChartOfAccounts] = useState<string>('SKR03')
  const [consultantNumber, setConsultantNumber] = useState('')
  const [clientNumber, setClientNumber] = useState('')

  // DATEV queries
  const { data: datevBatches = [], isLoading: isLoadingDatev } = useQuery({
    queryKey: ['datev-batches'],
    queryFn: getDatevBatches,
    refetchInterval: 30000,
  })

  // Lexware queries
  const { data: lexwareExports = [], isLoading: isLoadingExports } = useQuery({
    queryKey: ['lexware-exports'],
    queryFn: getLexwareExports,
    refetchInterval: 10000,
  })

  // Mutations
  const createDatevMutation = useMutation({
    mutationFn: createDatevBatch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datev-batches'] })
      toast({ title: 'Batch erstellt', description: 'DATEV Write-back Batch wurde erstellt' })
      setIsCreateDialogOpen(false)
      setConsultantNumber('')
      setClientNumber('')
    },
    onError: () => {
      toast({ title: 'Fehler', description: 'Batch konnte nicht erstellt werden', variant: 'destructive' })
    },
  })

  const confirmImportMutation = useMutation({
    mutationFn: confirmDatevImport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datev-batches'] })
      toast({ title: 'Import bestätigt', description: 'DATEV-Import wurde erfolgreich bestätigt' })
    },
  })

  const createLexwareMutation = useMutation({
    mutationFn: createLexwareExport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lexware-exports', 'lexware-stats'] })
      toast({ title: 'Export gestartet', description: 'Lexware-Export wurde gestartet' })
    },
  })

  const handleCreateDatevBatch = () => {
    if (!consultantNumber || !clientNumber) {
      toast({
        title: 'Fehlende Daten',
        description: 'Bitte füllen Sie alle Pflichtfelder aus',
        variant: 'destructive',
      })
      return
    }

    createDatevMutation.mutate({
      chart_of_accounts: chartOfAccounts as 'SKR03' | 'SKR04',
      consultant_number: consultantNumber,
      client_number: clientNumber,
    })
  }

  const handleDownloadDatev = async (batchId: string, fileName: string) => {
    try {
      const blob = await downloadDatevBatch(batchId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      toast({ title: 'Download fehlgeschlagen', variant: 'destructive' })
    }
  }

  const handleDownloadLexware = async (jobId: string, fileName: string) => {
    try {
      const blob = await downloadLexwareExport(jobId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      toast({ title: 'Download fehlgeschlagen', variant: 'destructive' })
    }
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ArrowLeftRight className="h-6 w-6" />
          Integrations-Synchronisation
        </h1>
        <p className="text-muted-foreground">
          DATEV Write-back und Lexware bidirektionaler Export
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="datev">DATEV Write-back</TabsTrigger>
          <TabsTrigger value="lexware">Lexware Export</TabsTrigger>
        </TabsList>

        <TabsContent value="datev" className="space-y-4">
          <div className="flex justify-end">
            <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
              <DialogTrigger asChild>
                <Button>
                  <Upload className="h-4 w-4 mr-2" />
                  Neuen Batch erstellen
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>DATEV Write-back Batch erstellen</DialogTitle>
                  <DialogDescription>
                    Erstellen Sie einen neuen Export-Batch für DATEV
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label>Kontenrahmen</Label>
                    <Select value={chartOfAccounts} onValueChange={setChartOfAccounts}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="SKR03">SKR03</SelectItem>
                        <SelectItem value="SKR04">SKR04</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Beraternummer</Label>
                    <Input
                      value={consultantNumber}
                      onChange={(e) => setConsultantNumber(e.target.value)}
                      placeholder="z.B. 12345"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Mandantennummer</Label>
                    <Input
                      value={clientNumber}
                      onChange={(e) => setClientNumber(e.target.value)}
                      placeholder="z.B. 67890"
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                    Abbrechen
                  </Button>
                  <Button onClick={handleCreateDatevBatch} disabled={createDatevMutation.isPending}>
                    {createDatevMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : null}
                    Erstellen
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>DATEV Write-back Batches</CardTitle>
              <CardDescription>Export von Buchungsdaten zurück an DATEV</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingDatev ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : !datevBatches.length ? (
                <div className="text-center py-8 text-muted-foreground">
                  Keine Batches vorhanden
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Kontenrahmen</TableHead>
                      <TableHead>Berater-Nr</TableHead>
                      <TableHead>Mandanten-Nr</TableHead>
                      <TableHead>Datensätze</TableHead>
                      <TableHead>Erstellt</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {datevBatches.map((batch) => (
                      <TableRow key={batch.id}>
                        <TableCell>
                          <Badge variant="outline">{batch.chart_of_accounts}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {batch.consultant_number}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{batch.client_number}</TableCell>
                        <TableCell>{batch.records_count}</TableCell>
                        <TableCell>
                          {new Date(batch.created_at).toLocaleDateString('de-DE')}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              batch.status === 'imported'
                                ? 'default'
                                : batch.status === 'exported'
                                ? 'secondary'
                                : 'outline'
                            }
                          >
                            {batch.status === 'draft'
                              ? 'Entwurf'
                              : batch.status === 'ready'
                              ? 'Bereit'
                              : batch.status === 'exported'
                              ? 'Exportiert'
                              : 'Importiert'}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            {batch.status !== 'draft' && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() =>
                                  handleDownloadDatev(
                                    batch.id,
                                    `datev-${batch.chart_of_accounts}-${batch.id}.csv`
                                  )
                                }
                              >
                                <Download className="h-3 w-3 mr-1" />
                                CSV
                              </Button>
                            )}
                            {batch.status === 'exported' && (
                              <Button
                                size="sm"
                                onClick={() => confirmImportMutation.mutate(batch.id)}
                                disabled={confirmImportMutation.isPending}
                              >
                                {confirmImportMutation.isPending ? (
                                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                ) : (
                                  <CheckCircle2 className="h-3 w-3 mr-1" />
                                )}
                                Import bestätigen
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="lexware" className="space-y-4">
          <div className="grid md:grid-cols-3 gap-4">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  Kunden
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">Kunden-Stammdaten exportieren</p>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => createLexwareMutation.mutate('customers')}
                  disabled={createLexwareMutation.isPending}
                >
                  {createLexwareMutation.isPending ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <Upload className="h-3 w-3 mr-1" />
                  )}
                  Export starten
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Building2 className="h-4 w-4" />
                  Lieferanten
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">Lieferanten-Stammdaten exportieren</p>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => createLexwareMutation.mutate('suppliers')}
                  disabled={createLexwareMutation.isPending}
                >
                  {createLexwareMutation.isPending ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <Upload className="h-3 w-3 mr-1" />
                  )}
                  Export starten
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <CreditCard className="h-4 w-4" />
                  Zahlungsstatus
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">Zahlungsstatus-Updates exportieren</p>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => createLexwareMutation.mutate('payment_status')}
                  disabled={createLexwareMutation.isPending}
                >
                  {createLexwareMutation.isPending ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <Upload className="h-3 w-3 mr-1" />
                  )}
                  Export starten
                </Button>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Letzte Exports</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoadingExports ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : !lexwareExports.length ? (
                <div className="text-center py-8 text-muted-foreground">Keine Exports vorhanden</div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Typ</TableHead>
                      <TableHead>Datensätze</TableHead>
                      <TableHead>Erstellt</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {lexwareExports.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell>
                          <Badge variant="outline">
                            {job.export_type === 'customers'
                              ? 'Kunden'
                              : job.export_type === 'suppliers'
                              ? 'Lieferanten'
                              : 'Zahlungen'}
                          </Badge>
                        </TableCell>
                        <TableCell>{job.records_count}</TableCell>
                        <TableCell>
                          {new Date(job.created_at).toLocaleDateString('de-DE', {
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              job.status === 'completed'
                                ? 'default'
                                : job.status === 'failed'
                                ? 'destructive'
                                : 'secondary'
                            }
                          >
                            {job.status === 'running' && (
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            )}
                            {job.status === 'pending' && <Clock className="h-3 w-3 mr-1" />}
                            {job.status === 'completed' && (
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                            )}
                            {job.status === 'pending'
                              ? 'Wartend'
                              : job.status === 'running'
                              ? 'Läuft'
                              : job.status === 'completed'
                              ? 'Abgeschlossen'
                              : 'Fehler'}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {job.status === 'completed' && job.file_path && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                handleDownloadLexware(
                                  job.id,
                                  `lexware-${job.export_type}-${job.id}.csv`
                                )
                              }
                            >
                              <Download className="h-3 w-3 mr-1" />
                              Download
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
