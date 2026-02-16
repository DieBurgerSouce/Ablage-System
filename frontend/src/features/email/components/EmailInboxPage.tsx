/**
 * E-Mail Import - Posteingang, Monitoring, Regeln und Konfiguration
 */
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, RefreshCw, Loader2, Paperclip, Plus } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { useLastActiveView } from '@/hooks/use-last-active-view'
import { EmlDropZone } from './EmlDropZone'
import { EmlPreviewDialog } from './EmlPreviewDialog'
import { ImportMonitoringPanel } from './ImportMonitoringPanel'
import { EmailConfigWizard } from './EmailConfigWizard'
import { EmailImportRuleBuilder as ImportRuleBuilder } from './ImportRuleBuilder'
import { uploadEmlFile, importEmlAttachments, emailImportKeys } from '../api/email-import-api'
import type { EmlParseResponse, EmlImportRequest, ImportRule } from '../types/email-types'

// Types (kept for backward compat with existing inline API calls)
interface EmailConfig {
  imap_host: string
  imap_port: number
  imap_ssl: boolean
  username: string
  folder: string
  auto_import_enabled: boolean
  auto_import_interval_minutes: number
  allowed_senders: string[]
  max_attachment_size_mb: number
}

interface ImportedEmail {
  id: string
  subject: string
  sender: string
  received_at: string
  attachments_count: number
  documents_created: number
  status: string  // "imported" | "skipped" | "error"
}

interface EmailImportStats {
  total_imported: number
  total_attachments: number
  documents_created: number
  last_check: string | null
  errors_count: number
}

const API_BASE = '/api/v1'

async function getEmailConfig(): Promise<EmailConfig> {
  const res = await fetch(`${API_BASE}/imports/email/config`)
  if (!res.ok) throw new Error('Fehler beim Laden der E-Mail-Konfiguration')
  return res.json()
}

async function updateEmailConfig(config: EmailConfig): Promise<EmailConfig> {
  const res = await fetch(`${API_BASE}/imports/email/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error('Fehler beim Speichern')
  return res.json()
}

async function getImportedEmails(limit: number = 50): Promise<{ items: ImportedEmail[]; total: number }> {
  const res = await fetch(`${API_BASE}/imports/email/history?limit=${limit}`)
  if (!res.ok) throw new Error('Fehler beim Laden')
  return res.json()
}

async function getEmailStats(): Promise<EmailImportStats> {
  const res = await fetch(`${API_BASE}/imports/email/stats`)
  if (!res.ok) throw new Error('Fehler beim Laden')
  return res.json()
}

async function triggerImport(): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/imports/email/trigger`, { method: 'POST' })
  if (!res.ok) throw new Error('Fehler beim Abrufen')
  return res.json()
}

export function EmailInboxPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useLastActiveView('email-inbox', 'inbox')
  const [configForm, setConfigForm] = useState<EmailConfig | null>(null)
  const [parsedEmail, setParsedEmail] = useState<EmlParseResponse | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [showWizard, setShowWizard] = useState(false)

  const { data: config, isLoading: isLoadingConfig } = useQuery({
    queryKey: ['email-config'],
    queryFn: getEmailConfig,
  })

  // Sync config form state when data loads
  useEffect(() => {
    if (config && !configForm) setConfigForm(config)
  }, [config, configForm])

  const { data: emails, isLoading: isLoadingEmails } = useQuery({
    queryKey: ['email-history'],
    queryFn: () => getImportedEmails(),
    refetchInterval: 30000,
  })

  const { data: stats } = useQuery({
    queryKey: ['email-stats'],
    queryFn: getEmailStats,
    refetchInterval: 30000,
  })

  const updateMutation = useMutation({
    mutationFn: updateEmailConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-config'] })
      toast({ title: 'Gespeichert', description: 'E-Mail-Konfiguration aktualisiert' })
    },
    onError: () => {
      toast({ title: 'Fehler', description: 'Konfiguration konnte nicht gespeichert werden', variant: 'destructive' })
    },
  })

  const triggerMutation = useMutation({
    mutationFn: triggerImport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-history', 'email-stats'] })
      toast({ title: 'Import gestartet', description: 'E-Mail-Abruf wurde ausgelöst' })
    },
  })

  // EML upload mutation
  const uploadMutation = useMutation({
    mutationFn: uploadEmlFile,
    onSuccess: (data) => {
      setParsedEmail(data)
      setShowPreview(true)
    },
    onError: () => {
      toast({ title: 'Fehler', description: 'E-Mail konnte nicht verarbeitet werden', variant: 'destructive' })
    },
  })

  // EML import mutation
  const importMutation = useMutation({
    mutationFn: importEmlAttachments,
    onSuccess: (data) => {
      setShowPreview(false)
      setParsedEmail(null)
      toast({ title: 'Import erfolgreich', description: `${data.imported_count} Dokument(e) importiert` })
      queryClient.invalidateQueries({ queryKey: emailImportKeys.all })
      queryClient.invalidateQueries({ queryKey: ['email-history'] })
      queryClient.invalidateQueries({ queryKey: ['email-stats'] })
    },
    onError: () => {
      toast({ title: 'Import fehlgeschlagen', description: 'Beim Import ist ein Fehler aufgetreten', variant: 'destructive' })
    },
  })

  const handleConfigChange = (field: keyof EmailConfig, value: string | number | boolean) => {
    if (configForm) setConfigForm({ ...configForm, [field]: value })
  }

  const handleRuleSave = (_rule: ImportRule) => {
    toast({ title: 'Regel gespeichert', description: 'Die Import-Regel wurde erfolgreich gespeichert' })
  }

  return (
    <EmlDropZone
      onFilesAccepted={(files) => files.forEach((f) => uploadMutation.mutate(f))}
      onError={(msg) => toast({ title: 'Ungültige Datei', description: msg, variant: 'destructive' })}
    >
      <div className="container mx-auto py-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Mail className="h-6 w-6" />
              E-Mail-Import
            </h1>
            <p className="text-muted-foreground">E-Mails importieren, überwachen und Regeln verwalten</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => setShowWizard(true)}>
              <Plus className="mr-2 h-4 w-4" /> Konfiguration hinzufügen
            </Button>
            <Button onClick={() => triggerMutation.mutate()} disabled={triggerMutation.isPending}>
              {triggerMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Jetzt abrufen
            </Button>
          </div>
        </div>

        {/* Stats cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{stats.total_imported}</div>
                <p className="text-xs text-muted-foreground">E-Mails importiert</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{stats.documents_created}</div>
                <p className="text-xs text-muted-foreground">Dokumente erstellt</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{stats.total_attachments}</div>
                <p className="text-xs text-muted-foreground">Anhänge verarbeitet</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">{stats.errors_count}</div>
                <p className="text-xs text-muted-foreground">Fehler</p>
              </CardContent>
            </Card>
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="inbox">Posteingang</TabsTrigger>
            <TabsTrigger value="monitoring">Monitoring</TabsTrigger>
            <TabsTrigger value="rules">Regeln</TabsTrigger>
            <TabsTrigger value="config">Konfiguration</TabsTrigger>
          </TabsList>

          <TabsContent value="inbox" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Importierte E-Mails</CardTitle>
              </CardHeader>
              <CardContent>
                {isLoadingEmails ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : !emails?.items.length ? (
                  <div className="text-center py-8 text-muted-foreground">
                    Keine importierten E-Mails
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Betreff</TableHead>
                        <TableHead>Absender</TableHead>
                        <TableHead>Empfangen</TableHead>
                        <TableHead>Anhänge</TableHead>
                        <TableHead>Dokumente</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {emails.items.map((email) => (
                        <TableRow key={email.id}>
                          <TableCell className="font-medium max-w-[200px] truncate">
                            {email.subject}
                          </TableCell>
                          <TableCell>{email.sender}</TableCell>
                          <TableCell>
                            {new Date(email.received_at).toLocaleDateString('de-DE', {
                              day: '2-digit',
                              month: '2-digit',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-1">
                              <Paperclip className="h-3 w-3" />
                              {email.attachments_count}
                            </div>
                          </TableCell>
                          <TableCell>{email.documents_created}</TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                email.status === 'imported'
                                  ? 'default'
                                  : email.status === 'error'
                                  ? 'destructive'
                                  : 'secondary'
                              }
                            >
                              {email.status === 'imported'
                                ? 'Importiert'
                                : email.status === 'error'
                                ? 'Fehler'
                                : 'Übersprungen'}
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

          <TabsContent value="monitoring" className="space-y-4">
            <ImportMonitoringPanel />
          </TabsContent>

          <TabsContent value="rules" className="space-y-4">
            <ImportRuleBuilder onSave={handleRuleSave} onCancel={() => setActiveTab('inbox')} />
          </TabsContent>

          <TabsContent value="config" className="space-y-4">
            {isLoadingConfig || !configForm ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle>IMAP-Server</CardTitle>
                    <CardDescription>Verbindungsdaten für den E-Mail-Server</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label>Server</Label>
                        <Input
                          value={configForm.imap_host}
                          onChange={(e) => handleConfigChange('imap_host', e.target.value)}
                          placeholder="imap.example.com"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Port</Label>
                        <Input
                          type="number"
                          value={configForm.imap_port}
                          onChange={(e) =>
                            handleConfigChange('imap_port', parseInt(e.target.value) || 993)
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Benutzername</Label>
                        <Input
                          value={configForm.username}
                          onChange={(e) => handleConfigChange('username', e.target.value)}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Ordner</Label>
                        <Input
                          value={configForm.folder}
                          onChange={(e) => handleConfigChange('folder', e.target.value)}
                          placeholder="INBOX"
                        />
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={configForm.imap_ssl}
                        onCheckedChange={(v) => handleConfigChange('imap_ssl', v)}
                      />
                      <Label>SSL/TLS verwenden</Label>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Automatisierung</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <Label>Automatischer Import</Label>
                        <p className="text-xs text-muted-foreground">
                          E-Mails werden automatisch abgerufen und Anhänge importiert
                        </p>
                      </div>
                      <Switch
                        checked={configForm.auto_import_enabled}
                        onCheckedChange={(v) => handleConfigChange('auto_import_enabled', v)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Intervall (Minuten)</Label>
                      <Input
                        type="number"
                        min={5}
                        max={1440}
                        value={configForm.auto_import_interval_minutes}
                        onChange={(e) =>
                          handleConfigChange(
                            'auto_import_interval_minutes',
                            parseInt(e.target.value) || 60
                          )
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Max. Anhang-Größe (MB)</Label>
                      <Input
                        type="number"
                        min={1}
                        max={100}
                        value={configForm.max_attachment_size_mb}
                        onChange={(e) =>
                          handleConfigChange(
                            'max_attachment_size_mb',
                            parseInt(e.target.value) || 50
                          )
                        }
                      />
                    </div>
                  </CardContent>
                </Card>
                <div className="flex justify-end">
                  <Button
                    onClick={() => updateMutation.mutate(configForm)}
                    disabled={updateMutation.isPending}
                  >
                    {updateMutation.isPending ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : null}
                    Konfiguration speichern
                  </Button>
                </div>
              </>
            )}
          </TabsContent>
        </Tabs>

        {/* EML Preview Dialog */}
        <EmlPreviewDialog
          open={showPreview}
          onOpenChange={setShowPreview}
          parsedEmail={parsedEmail}
          onImport={(req: EmlImportRequest) => importMutation.mutate(req)}
          isImporting={importMutation.isPending}
        />

        {/* Config Wizard Dialog */}
        {showWizard && (
          <EmailConfigWizard
            onComplete={() => {
              setShowWizard(false)
              queryClient.invalidateQueries({ queryKey: ['email-config'] })
              toast({ title: 'Konfiguration erstellt', description: 'Die E-Mail-Konfiguration wurde erfolgreich eingerichtet' })
            }}
            onCancel={() => setShowWizard(false)}
          />
        )}
      </div>
    </EmlDropZone>
  )
}
