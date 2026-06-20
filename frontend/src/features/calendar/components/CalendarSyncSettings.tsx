/**
 * Kalender-Synchronisation Konfiguration
 *
 * 4-Tab-Interface: Export | Sync-Provider | Vorschau | Status
 * Behält die bestehende iCal-Export-Funktionalität im Export-Tab
 * und integriert die neuen OAuth/Sync-Komponenten.
 */
import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Calendar, Download, Settings, Loader2, Info } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Checkbox } from '@/components/ui/checkbox'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { useLastActiveView } from '@/hooks/use-last-active-view'
import { OAuthConnectButton } from './OAuthConnectButton'
import { OAuthSetupCard } from './OAuthSetupCard'
import { CalendarPreviewPanel } from './CalendarPreviewPanel'
import { SyncStatusDashboard } from './SyncStatusDashboard'
import {
  getOAuthStatus,
  startOAuthFlow,
  revokeOAuth,
  calendarSyncKeys,
} from '../api/calendar-sync-api'

// Types for local iCal config (kept from original)
interface CalendarSyncConfig {
  provider: 'ical' | 'caldav' | 'google' | 'outlook'
  caldav_url: string | null
  username: string | null
  sync_interval_minutes: number
  auto_sync_enabled: boolean
  export_categories: {
    payment_deadlines: boolean
    skonto_deadlines: boolean
    contract_deadlines: boolean
    dunning_deadlines: boolean
  }
  days_ahead: number
}

interface ExportParams {
  categories: string[]
  days_ahead: number
}

const API_BASE = '/api/v1'

async function getCalendarSyncConfig(): Promise<CalendarSyncConfig> {
  const res = await fetch(`${API_BASE}/calendar-sync/config`)
  if (!res.ok) throw new Error('Fehler beim Laden der Konfiguration')
  return res.json()
}

async function updateCalendarSyncConfig(config: CalendarSyncConfig): Promise<CalendarSyncConfig> {
  const res = await fetch(`${API_BASE}/calendar-sync/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error('Fehler beim Speichern')
  return res.json()
}

async function downloadICalExport(params: ExportParams): Promise<Blob> {
  const queryParams = new URLSearchParams({
    categories: params.categories.join(','),
    days_ahead: params.days_ahead.toString(),
  })
  const res = await fetch(`${API_BASE}/calendar-sync/export.ics?${queryParams}`)
  if (!res.ok) throw new Error('Fehler beim Export')
  return res.blob()
}

export function CalendarSyncSettings() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useLastActiveView('calendar-sync', 'export')
  const [configForm, setConfigForm] = useState<CalendarSyncConfig | null>(null)

  // Existing config query (iCal export)
  const { data: existingConfig, isLoading } = useQuery({
    queryKey: ['calendar-sync-config'],
    queryFn: getCalendarSyncConfig,
  })

  // react-query v5 hat kein onSuccess mehr auf useQuery
  useEffect(() => {
    if (existingConfig && !configForm) setConfigForm(existingConfig)
  }, [existingConfig, configForm])

  // OAuth status query
  const { data: oauthStatus } = useQuery({
    queryKey: calendarSyncKeys.oauthStatus(),
    queryFn: getOAuthStatus,
  })

  // Existing config update mutation
  const updateMutation = useMutation({
    mutationFn: updateCalendarSyncConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['calendar-sync-config'] })
      toast({ title: 'Gespeichert', description: 'Kalender-Synchronisation aktualisiert' })
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Konfiguration konnte nicht gespeichert werden',
        variant: 'destructive',
      })
    },
  })

  // OAuth flow mutation
  const startOAuth = useMutation({
    mutationFn: startOAuthFlow,
    onSuccess: (data) => {
      window.open(data.auth_url, 'oauth-popup', 'width=600,height=700')
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'OAuth-Verbindung konnte nicht gestartet werden',
        variant: 'destructive',
      })
    },
  })

  const revokeOAuthMutation = useMutation({
    mutationFn: revokeOAuth,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: calendarSyncKeys.oauthStatus() })
      toast({ title: 'Verbindung getrennt', description: 'OAuth-Verbindung wurde erfolgreich getrennt' })
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Verbindung konnte nicht getrennt werden',
        variant: 'destructive',
      })
    },
  })

  // Existing handlers (iCal export)
  const handleConfigChange = (field: keyof CalendarSyncConfig, value: unknown) => {
    if (configForm) {
      setConfigForm({ ...configForm, [field]: value })
    }
  }

  const handleCategoryChange = (category: keyof CalendarSyncConfig['export_categories'], value: boolean) => {
    if (configForm) {
      setConfigForm({
        ...configForm,
        export_categories: { ...configForm.export_categories, [category]: value },
      })
    }
  }

  const handleExportDownload = async () => {
    if (!configForm) return

    const categories: string[] = []
    if (configForm.export_categories.payment_deadlines) categories.push('payment')
    if (configForm.export_categories.skonto_deadlines) categories.push('skonto')
    if (configForm.export_categories.contract_deadlines) categories.push('contract')
    if (configForm.export_categories.dunning_deadlines) categories.push('dunning')

    if (categories.length === 0) {
      toast({
        title: 'Keine Kategorien ausgewählt',
        description: 'Bitte wählen Sie mindestens eine Kategorie aus',
        variant: 'destructive',
      })
      return
    }

    try {
      const blob = await downloadICalExport({
        categories,
        days_ahead: configForm.days_ahead,
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ablage-kalender-${new Date().toISOString().split('T')[0]}.ics`
      a.click()
      window.URL.revokeObjectURL(url)
      toast({ title: 'Export erfolgreich', description: 'Kalenderdatei wurde heruntergeladen' })
    } catch {
      toast({
        title: 'Export fehlgeschlagen',
        description: 'Kalenderdatei konnte nicht erstellt werden',
        variant: 'destructive',
      })
    }
  }

  if (isLoading || !configForm) {
    return (
      <div className="container mx-auto py-6">
        <div className="flex justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Calendar className="h-6 w-6" />
          Kalender-Synchronisierung
        </h1>
        <p className="text-muted-foreground">
          Fristen und Termine mit externen Kalendern synchronisieren
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="export">Export</TabsTrigger>
          <TabsTrigger value="provider">Sync-Provider</TabsTrigger>
          <TabsTrigger value="preview">Vorschau</TabsTrigger>
          <TabsTrigger value="status">Status</TabsTrigger>
        </TabsList>

        {/* === Export Tab: All existing iCal export + config content === */}
        <TabsContent value="export" className="mt-4 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Download className="h-5 w-5" />
                iCal-Export
              </CardTitle>
              <CardDescription>
                Kalender-Datei (.ics) für Import in Outlook, Google Kalender, Apple Kalender, etc.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label className="mb-3 block">Zu exportierende Kategorien</Label>
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={configForm.export_categories.payment_deadlines}
                      onCheckedChange={(v) =>
                        handleCategoryChange('payment_deadlines', v as boolean)
                      }
                    />
                    <Label className="font-normal">Zahlungsfristen</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={configForm.export_categories.skonto_deadlines}
                      onCheckedChange={(v) => handleCategoryChange('skonto_deadlines', v as boolean)}
                    />
                    <Label className="font-normal">Skonto-Fristen</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={configForm.export_categories.contract_deadlines}
                      onCheckedChange={(v) =>
                        handleCategoryChange('contract_deadlines', v as boolean)
                      }
                    />
                    <Label className="font-normal">Vertragsfristen</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={configForm.export_categories.dunning_deadlines}
                      onCheckedChange={(v) => handleCategoryChange('dunning_deadlines', v as boolean)}
                    />
                    <Label className="font-normal">Mahnfristen</Label>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Zeitraum (Tage im Voraus)</Label>
                <div className="flex items-center gap-4">
                  <Slider
                    value={[configForm.days_ahead]}
                    onValueChange={(v) => handleConfigChange('days_ahead', v[0])}
                    min={30}
                    max={365}
                    step={30}
                    className="flex-1"
                  />
                  <Badge variant="secondary" className="min-w-[60px] justify-center">
                    {configForm.days_ahead} Tage
                  </Badge>
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={handleExportDownload}>
                  <Download className="h-4 w-4 mr-2" />
                  .ics-Datei herunterladen
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Sync-Konfiguration
              </CardTitle>
              <CardDescription>Automatische Synchronisation mit externen Kalendern</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Provider</Label>
                <Select
                  value={configForm.provider}
                  onValueChange={(v) => handleConfigChange('provider', v)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ical">iCal-Datei (manueller Download)</SelectItem>
                    <SelectItem value="caldav">CalDAV (Nextcloud, ownCloud)</SelectItem>
                    <SelectItem value="google">Google Kalender</SelectItem>
                    <SelectItem value="outlook">Microsoft Outlook</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {configForm.provider === 'caldav' && (
                <>
                  <div className="space-y-2">
                    <Label>CalDAV-URL</Label>
                    <Input
                      value={configForm.caldav_url || ''}
                      onChange={(e) => handleConfigChange('caldav_url', e.target.value)}
                      placeholder="https://cloud.example.com/remote.php/dav/calendars/user/ablage/"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Benutzername</Label>
                    <Input
                      value={configForm.username || ''}
                      onChange={(e) => handleConfigChange('username', e.target.value)}
                    />
                  </div>
                </>
              )}

              <div className="flex items-center justify-between">
                <div>
                  <Label>Automatische Synchronisation</Label>
                  <p className="text-xs text-muted-foreground">
                    Kalender wird automatisch mit dem Provider synchronisiert
                  </p>
                </div>
                <Switch
                  checked={configForm.auto_sync_enabled}
                  onCheckedChange={(v) => handleConfigChange('auto_sync_enabled', v)}
                />
              </div>

              {configForm.auto_sync_enabled && (
                <div className="space-y-2">
                  <Label>Sync-Intervall (Minuten)</Label>
                  <Input
                    type="number"
                    min={15}
                    max={1440}
                    value={configForm.sync_interval_minutes}
                    onChange={(e) =>
                      handleConfigChange('sync_interval_minutes', parseInt(e.target.value) || 60)
                    }
                  />
                </div>
              )}

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
            </CardContent>
          </Card>

          <Card className="border-blue-200 bg-blue-50/50">
            <CardContent className="pt-6">
              <div className="flex gap-3">
                <Info className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div className="space-y-2 text-sm">
                  <p className="font-medium">Provider-Informationen:</p>
                  <ul className="space-y-1 list-disc list-inside text-muted-foreground">
                    <li>
                      <strong>iCal-Datei:</strong> Manuelle Downloads, kompatibel mit allen Kalender-Apps
                    </li>
                    <li>
                      <strong>CalDAV:</strong> Automatische Sync mit Nextcloud, ownCloud, etc.
                    </li>
                    <li>
                      <strong>Google Kalender:</strong> Direktintegration (OAuth erforderlich)
                    </li>
                    <li>
                      <strong>Outlook:</strong> Microsoft 365 Integration (OAuth erforderlich)
                    </li>
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* === Provider Tab: OAuth setup + connection buttons === */}
        <TabsContent value="provider" className="mt-4 space-y-6">
          <OAuthSetupCard />
          {oauthStatus && (
            <div className="space-y-4">
              <h3 className="text-lg font-medium">Verbundene Konten</h3>
              <div className="grid gap-4 md:grid-cols-2">
                <OAuthConnectButton
                  provider="google"
                  status={oauthStatus.google}
                  onConnect={() =>
                    startOAuth.mutate({
                      provider: 'google',
                      client_id: '',
                      client_secret: '',
                      redirect_uri: `${window.location.origin}/api/v1/calendar-sync/oauth/callback`,
                    })
                  }
                  onDisconnect={() => revokeOAuthMutation.mutate('google')}
                  isLoading={startOAuth.isPending}
                />
                <OAuthConnectButton
                  provider="outlook"
                  status={oauthStatus.outlook}
                  onConnect={() =>
                    startOAuth.mutate({
                      provider: 'outlook',
                      client_id: '',
                      client_secret: '',
                      redirect_uri: `${window.location.origin}/api/v1/calendar-sync/oauth/callback`,
                    })
                  }
                  onDisconnect={() => revokeOAuthMutation.mutate('outlook')}
                  isLoading={startOAuth.isPending}
                />
              </div>
            </div>
          )}
        </TabsContent>

        {/* === Preview Tab === */}
        <TabsContent value="preview" className="mt-4">
          <CalendarPreviewPanel />
        </TabsContent>

        {/* === Status Tab === */}
        <TabsContent value="status" className="mt-4">
          <SyncStatusDashboard />
        </TabsContent>
      </Tabs>
    </div>
  )
}
