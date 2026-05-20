/**
 * EndpointDialog
 *
 * Dialog zum Erstellen und Bearbeiten von Webhook-Endpoints.
 */

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, Plus, X } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useCreateEndpoint, useUpdateEndpoint } from '../api'
import type {
  WebhookEndpointResponse,
  WebhookEndpointWithSecret,
  RetryPolicy,
} from '../types'
import { DEFAULT_RETRY_POLICY, COMMON_EVENT_TYPES } from '../types'

interface EndpointDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  endpoint: WebhookEndpointResponse | null
  onCreated?: (endpoint: WebhookEndpointWithSecret) => void
}

export function EndpointDialog({
  open,
  onOpenChange,
  endpoint,
  onCreated,
}: EndpointDialogProps) {
  const isEdit = !!endpoint

  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [eventTypes, setEventTypes] = useState<string[]>([])
  const [newEventType, setNewEventType] = useState('')
  const [maxRetries, setMaxRetries] = useState(DEFAULT_RETRY_POLICY.max_retries)
  const [backoffFactor, setBackoffFactor] = useState(DEFAULT_RETRY_POLICY.backoff_factor)
  const [timeoutSeconds, setTimeoutSeconds] = useState(DEFAULT_RETRY_POLICY.timeout_seconds)
  const [customHeaders, setCustomHeaders] = useState('')

  const createMutation = useCreateEndpoint()
  const updateMutation = useUpdateEndpoint()

  useEffect(() => {
    if (open) {
      if (endpoint) {
        setUrl(endpoint.url)
        setDescription(endpoint.description ?? '')
        setEventTypes(endpoint.event_types)
        setNewEventType('')
        setMaxRetries(endpoint.retry_policy?.max_retries ?? DEFAULT_RETRY_POLICY.max_retries)
        setBackoffFactor(endpoint.retry_policy?.backoff_factor ?? DEFAULT_RETRY_POLICY.backoff_factor)
        setTimeoutSeconds(endpoint.retry_policy?.timeout_seconds ?? DEFAULT_RETRY_POLICY.timeout_seconds)
        setCustomHeaders(
          endpoint.headers
            ? Object.entries(endpoint.headers)
                .map(([k, v]) => `${k}: ${v}`)
                .join('\n')
            : ''
        )
      } else {
        setUrl('')
        setDescription('')
        setEventTypes([])
        setNewEventType('')
        setMaxRetries(DEFAULT_RETRY_POLICY.max_retries)
        setBackoffFactor(DEFAULT_RETRY_POLICY.backoff_factor)
        setTimeoutSeconds(DEFAULT_RETRY_POLICY.timeout_seconds)
        setCustomHeaders('')
      }
    }
  }, [open, endpoint])

  const addEventType = (et: string) => {
    const trimmed = et.trim()
    if (trimmed && !eventTypes.includes(trimmed)) {
      setEventTypes([...eventTypes, trimmed])
    }
    setNewEventType('')
  }

  const removeEventType = (et: string) => {
    setEventTypes(eventTypes.filter((t) => t !== et))
  }

  const parseHeaders = (): Record<string, string> | undefined => {
    if (!customHeaders.trim()) return undefined
    const result: Record<string, string> = {}
    for (const line of customHeaders.split('\n')) {
      const colonIdx = line.indexOf(':')
      if (colonIdx > 0) {
        const key = line.slice(0, colonIdx).trim()
        const val = line.slice(colonIdx + 1).trim()
        if (key && val) result[key] = val
      }
    }
    return Object.keys(result).length > 0 ? result : undefined
  }

  const handleSave = async () => {
    if (!url.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie eine URL ein.',
        variant: 'destructive',
      })
      return
    }

    const retryPolicy: RetryPolicy = {
      max_retries: maxRetries,
      backoff_factor: backoffFactor,
      timeout_seconds: timeoutSeconds,
    }

    try {
      if (isEdit) {
        await updateMutation.mutateAsync({
          id: endpoint.id,
          data: {
            url: url.trim(),
            description: description.trim() || undefined,
            event_types: eventTypes,
            headers: parseHeaders(),
            retry_policy: retryPolicy,
          },
        })
        toast({
          title: 'Endpoint aktualisiert',
          description: 'Die Konfiguration wurde gespeichert.',
        })
        onOpenChange(false)
      } else {
        const created = await createMutation.mutateAsync({
          url: url.trim(),
          description: description.trim() || undefined,
          event_types: eventTypes,
          headers: parseHeaders(),
          retry_policy: retryPolicy,
        })
        toast({
          title: 'Endpoint registriert',
          description: 'Der Webhook-Endpoint wurde erstellt.',
        })
        onOpenChange(false)
        onCreated?.(created)
      }
    } catch {
      toast({
        title: 'Fehler',
        description: 'Der Endpoint konnte nicht gespeichert werden.',
        variant: 'destructive',
      })
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? 'Endpoint bearbeiten' : 'Neuer Webhook-Endpoint'}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Aktualisieren Sie die Endpoint-Konfiguration.'
              : 'Registrieren Sie einen neuen Outbound-Webhook-Endpoint.'}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 pr-4">
          <div className="space-y-6 py-4">
            {/* URL */}
            <div className="space-y-2">
              <Label htmlFor="wh-url">Ziel-URL *</Label>
              <Input
                id="wh-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/webhooks"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                HTTPS wird empfohlen. Maximal 2000 Zeichen.
              </p>
            </div>

            {/* Beschreibung */}
            <div className="space-y-2">
              <Label htmlFor="wh-desc">Beschreibung</Label>
              <Textarea
                id="wh-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optionale Beschreibung des Endpoints"
                rows={2}
              />
            </div>

            {/* Event-Typen */}
            <div className="space-y-3">
              <Label>Event-Typen</Label>
              <p className="text-xs text-muted-foreground">
                Leer = alle Events. Klicken Sie auf gaengige Typen oder fuegen Sie eigene hinzu.
              </p>

              <div className="flex flex-wrap gap-1">
                {eventTypes.map((et) => (
                  <Badge key={et} variant="secondary" className="gap-1">
                    {et}
                    <button
                      onClick={() => removeEventType(et)}
                      className="ml-1 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>

              <div className="flex gap-2">
                <Input
                  value={newEventType}
                  onChange={(e) => setNewEventType(e.target.value)}
                  placeholder="z.B. document.created"
                  className="font-mono"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addEventType(newEventType)
                    }
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => addEventType(newEventType)}
                  disabled={!newEventType.trim()}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>

              <div className="flex flex-wrap gap-1">
                {COMMON_EVENT_TYPES.filter((et) => !eventTypes.includes(et)).map((et) => (
                  <Badge
                    key={et}
                    variant="outline"
                    className="cursor-pointer hover:bg-accent text-xs"
                    onClick={() => addEventType(et)}
                  >
                    + {et}
                  </Badge>
                ))}
              </div>
            </div>

            {/* Retry-Policy */}
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Retry-Richtlinie
              </h3>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Max. Versuche (0-10)</Label>
                  <Input
                    type="number"
                    value={maxRetries}
                    onChange={(e) => setMaxRetries(Math.min(10, Math.max(0, Number(e.target.value))))}
                    min={0}
                    max={10}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Backoff-Faktor (1-10)</Label>
                  <Input
                    type="number"
                    value={backoffFactor}
                    onChange={(e) => setBackoffFactor(Math.min(10, Math.max(1, Number(e.target.value))))}
                    min={1}
                    max={10}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Timeout (5-120s)</Label>
                  <Input
                    type="number"
                    value={timeoutSeconds}
                    onChange={(e) => setTimeoutSeconds(Math.min(120, Math.max(5, Number(e.target.value))))}
                    min={5}
                    max={120}
                  />
                </div>
              </div>
            </div>

            {/* Custom Headers */}
            <div className="space-y-2">
              <Label>Benutzerdefinierte HTTP-Header</Label>
              <Textarea
                value={customHeaders}
                onChange={(e) => setCustomHeaders(e.target.value)}
                placeholder={"X-Custom-Header: wert\nX-API-Version: 2"}
                rows={3}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                Ein Header pro Zeile im Format &quot;Name: Wert&quot;.
                Authorization, Content-Type und X-Webhook-Signature sind nicht erlaubt.
              </p>
            </div>

            {/* HMAC-Info */}
            {!isEdit && (
              <div className="rounded-md bg-muted/50 p-3 text-sm text-muted-foreground">
                <strong>Signatur-Hinweis:</strong> Nach der Erstellung erhalten Sie ein
                Secret (whsec_...). Verwenden Sie es zur HMAC-SHA256-Verifizierung
                der eingehenden Webhook-Payloads. Das Secret wird nur einmalig angezeigt.
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="border-t pt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSave} disabled={isPending}>
            {isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {isEdit ? 'Speichern' : 'Registrieren'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
