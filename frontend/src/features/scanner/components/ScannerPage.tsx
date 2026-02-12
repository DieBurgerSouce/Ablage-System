/**
 * Scanner-Verwaltung und Scan-Aufträge
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ScanLine, Loader2, CheckCircle2, AlertCircle, XCircle, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'

// Types
interface ScannerDevice {
  id: string
  name: string
  model: string
  manufacturer: string
  location: string
  status: 'online' | 'offline' | 'scanning'
  supports_adf: boolean
  supports_duplex: boolean
  max_resolution: number
  ip_address: string
}

interface ScanJob {
  id: string
  scanner_id: string
  scanner_name: string
  status: 'pending' | 'scanning' | 'completed' | 'failed'
  resolution: number
  color_mode: 'color' | 'grayscale' | 'bw'
  use_adf: boolean
  use_duplex: boolean
  pages_scanned: number
  documents_created: number
  created_at: string
  completed_at: string | null
  error_message: string | null
}

interface CreateScanJobRequest {
  scanner_id: string
  resolution: number
  color_mode: 'color' | 'grayscale' | 'bw'
  use_adf: boolean
  use_duplex: boolean
}

const API_BASE = '/api/v1'

async function getScanners(): Promise<ScannerDevice[]> {
  const res = await fetch(`${API_BASE}/scanner/devices`)
  if (!res.ok) throw new Error('Fehler beim Laden der Scanner')
  return res.json()
}

async function getScanJobs(limit: number = 50): Promise<ScanJob[]> {
  const res = await fetch(`${API_BASE}/scanner/jobs?limit=${limit}`)
  if (!res.ok) throw new Error('Fehler beim Laden der Scan-Aufträge')
  return res.json()
}

async function createScanJob(request: CreateScanJobRequest): Promise<ScanJob> {
  const res = await fetch(`${API_BASE}/scanner/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!res.ok) throw new Error('Fehler beim Erstellen des Scan-Auftrags')
  return res.json()
}

export function ScannerPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('devices')

  // Scan job form state
  const [selectedScanner, setSelectedScanner] = useState<string>('auto')
  const [resolution, setResolution] = useState<string>('300')
  const [colorMode, setColorMode] = useState<string>('color')
  const [useAdf, setUseAdf] = useState(false)
  const [useDuplex, setUseDuplex] = useState(false)

  const { data: scanners, isLoading: isLoadingScanners } = useQuery({
    queryKey: ['scanners'],
    queryFn: getScanners,
    refetchInterval: 10000,
  })

  const { data: jobs = [], isLoading: isLoadingJobs } = useQuery({
    queryKey: ['scan-jobs'],
    queryFn: () => getScanJobs(),
    refetchInterval: 5000,
  })

  const createJobMutation = useMutation({
    mutationFn: createScanJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scan-jobs'] })
      toast({ title: 'Scan-Auftrag erstellt', description: 'Der Scan-Vorgang wurde gestartet' })
      // Reset form
      setResolution('300')
      setColorMode('color')
      setUseAdf(false)
      setUseDuplex(false)
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Scan-Auftrag konnte nicht erstellt werden',
        variant: 'destructive',
      })
    },
  })

  const handleCreateJob = () => {
    if (selectedScanner === 'auto') {
      toast({
        title: 'Kein Scanner ausgewählt',
        description: 'Bitte wählen Sie einen Scanner aus',
        variant: 'destructive',
      })
      return
    }

    createJobMutation.mutate({
      scanner_id: selectedScanner,
      resolution: parseInt(resolution),
      color_mode: colorMode as 'color' | 'grayscale' | 'bw',
      use_adf: useAdf,
      use_duplex: useDuplex,
    })
  }

  const onlineScanners = scanners?.filter((s) => s.status === 'online').length || 0

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ScanLine className="h-6 w-6" />
            Scanner-Verwaltung
            {scanners && <Badge variant="secondary">{onlineScanners} online</Badge>}
          </h1>
          <p className="text-muted-foreground">Verwaltung von Netzwerk-Scannern und Scan-Aufträgen</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="devices">Scanner-Geräte</TabsTrigger>
          <TabsTrigger value="jobs">Scan-Aufträge</TabsTrigger>
        </TabsList>

        <TabsContent value="devices" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Registrierte Scanner</CardTitle>
              <CardDescription>Verfügbare Scanner-Geräte im Netzwerk</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingScanners ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : !scanners?.length ? (
                <div className="text-center py-8 text-muted-foreground">
                  Keine Scanner gefunden
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Modell</TableHead>
                      <TableHead>Standort</TableHead>
                      <TableHead>IP-Adresse</TableHead>
                      <TableHead>Funktionen</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {scanners.map((scanner) => (
                      <TableRow key={scanner.id}>
                        <TableCell className="font-medium">{scanner.name}</TableCell>
                        <TableCell>
                          {scanner.manufacturer} {scanner.model}
                        </TableCell>
                        <TableCell>{scanner.location}</TableCell>
                        <TableCell className="font-mono text-xs">{scanner.ip_address}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {scanner.supports_adf && (
                              <Badge variant="outline" className="text-xs">
                                ADF
                              </Badge>
                            )}
                            {scanner.supports_duplex && (
                              <Badge variant="outline" className="text-xs">
                                Duplex
                              </Badge>
                            )}
                            <Badge variant="outline" className="text-xs">
                              {scanner.max_resolution} DPI
                            </Badge>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              scanner.status === 'online'
                                ? 'default'
                                : scanner.status === 'scanning'
                                ? 'secondary'
                                : 'outline'
                            }
                          >
                            {scanner.status === 'online' && (
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                            )}
                            {scanner.status === 'scanning' && (
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            )}
                            {scanner.status === 'offline' && (
                              <XCircle className="h-3 w-3 mr-1" />
                            )}
                            {scanner.status === 'online'
                              ? 'Online'
                              : scanner.status === 'scanning'
                              ? 'Scannt'
                              : 'Offline'}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="jobs" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Neuer Scan-Auftrag</CardTitle>
              <CardDescription>Scan-Vorgang konfigurieren und starten</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Scanner</Label>
                  <Select value={selectedScanner} onValueChange={setSelectedScanner}>
                    <SelectTrigger>
                      <SelectValue placeholder="Scanner auswählen" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">Scanner auswählen</SelectItem>
                      {scanners
                        ?.filter((s) => s.status === 'online')
                        .map((scanner) => (
                          <SelectItem key={scanner.id} value={scanner.id}>
                            {scanner.name} ({scanner.location})
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Auflösung</Label>
                  <Select value={resolution} onValueChange={setResolution}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="150">150 DPI</SelectItem>
                      <SelectItem value="300">300 DPI</SelectItem>
                      <SelectItem value="600">600 DPI</SelectItem>
                      <SelectItem value="1200">1200 DPI</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Farbmodus</Label>
                  <Select value={colorMode} onValueChange={setColorMode}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="color">Farbe</SelectItem>
                      <SelectItem value="grayscale">Graustufen</SelectItem>
                      <SelectItem value="bw">Schwarz/Weiß</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex gap-6">
                <div className="flex items-center gap-2">
                  <Switch checked={useAdf} onCheckedChange={setUseAdf} />
                  <Label>Einzug (ADF)</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={useDuplex} onCheckedChange={setUseDuplex} />
                  <Label>Beidseitig (Duplex)</Label>
                </div>
              </div>

              <div className="flex justify-end">
                <Button
                  onClick={handleCreateJob}
                  disabled={createJobMutation.isPending || selectedScanner === 'auto'}
                >
                  {createJobMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : null}
                  Scan starten
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Letzte Scan-Aufträge</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoadingJobs ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : !jobs.length ? (
                <div className="text-center py-8 text-muted-foreground">
                  Keine Scan-Aufträge vorhanden
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Scanner</TableHead>
                      <TableHead>Konfiguration</TableHead>
                      <TableHead>Seiten</TableHead>
                      <TableHead>Dokumente</TableHead>
                      <TableHead>Erstellt</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.map((job) => (
                      <TableRow key={job.id}>
                        <TableCell className="font-medium">{job.scanner_name}</TableCell>
                        <TableCell>
                          <div className="text-xs space-y-1">
                            <div>{job.resolution} DPI</div>
                            <div className="flex gap-1">
                              {job.color_mode === 'color' && (
                                <Badge variant="outline" className="text-xs">
                                  Farbe
                                </Badge>
                              )}
                              {job.color_mode === 'grayscale' && (
                                <Badge variant="outline" className="text-xs">
                                  Grau
                                </Badge>
                              )}
                              {job.color_mode === 'bw' && (
                                <Badge variant="outline" className="text-xs">
                                  S/W
                                </Badge>
                              )}
                              {job.use_adf && (
                                <Badge variant="outline" className="text-xs">
                                  ADF
                                </Badge>
                              )}
                              {job.use_duplex && (
                                <Badge variant="outline" className="text-xs">
                                  Duplex
                                </Badge>
                              )}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>{job.pages_scanned}</TableCell>
                        <TableCell>{job.documents_created}</TableCell>
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
                                : job.status === 'scanning'
                                ? 'secondary'
                                : 'outline'
                            }
                          >
                            {job.status === 'completed' && (
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                            )}
                            {job.status === 'scanning' && (
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            )}
                            {job.status === 'failed' && <AlertCircle className="h-3 w-3 mr-1" />}
                            {job.status === 'pending' && <Clock className="h-3 w-3 mr-1" />}
                            {job.status === 'completed'
                              ? 'Abgeschlossen'
                              : job.status === 'scanning'
                              ? 'Scannt'
                              : job.status === 'failed'
                              ? 'Fehler'
                              : 'Wartend'}
                          </Badge>
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
