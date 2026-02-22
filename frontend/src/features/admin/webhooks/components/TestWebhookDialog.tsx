/**
 * TestWebhookDialog
 *
 * Dialog zum Senden einer Test-Zustellung an einen Webhook-Endpoint.
 */

import { useState } from 'react'
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
import { Loader2, Send } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'
import { useTestEndpoint } from '../api'
import type { WebhookEndpointResponse } from '../types'

interface TestWebhookDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  endpoint: WebhookEndpointResponse | null
}

export function TestWebhookDialog({
  open,
  onOpenChange,
  endpoint,
}: TestWebhookDialogProps) {
  const [eventType, setEventType] = useState('webhook.test')
  const testMutation = useTestEndpoint()

  const handleTest = async () => {
    if (!endpoint) return

    try {
      const result = await testMutation.mutateAsync({
        id: endpoint.id,
        data: { event_type: eventType.trim() || 'webhook.test' },
      })
      toast({
        title: 'Test gestartet',
        description: result.message,
      })
      onOpenChange(false)
    } catch {
      toast({
        title: 'Fehler',
        description: 'Die Test-Zustellung konnte nicht gestartet werden.',
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Test-Zustellung senden</DialogTitle>
          <DialogDescription>
            Sendet einen Test-Webhook an den konfigurierten Endpoint.
            Das Ergebnis ist in der Zustellungshistorie sichtbar.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="text-sm">
            <span className="text-muted-foreground">Endpoint: </span>
            <span className="font-mono text-xs">{endpoint?.url}</span>
          </div>

          <div className="space-y-2">
            <Label htmlFor="test-event-type">Event-Typ</Label>
            <Input
              id="test-event-type"
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              placeholder="webhook.test"
              className="font-mono"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleTest} disabled={testMutation.isPending}>
            {testMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Send className="h-4 w-4 mr-2" />
            )}
            Test senden
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
