/**
 * SecretRevealDialog
 *
 * Einmalige Anzeige des Webhook-Secrets nach der Erstellung.
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
import { Copy, Check, AlertTriangle } from 'lucide-react'
import { toast } from '@/components/ui/use-toast'

interface SecretRevealDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  secret: string
  endpointUrl: string
}

export function SecretRevealDialog({
  open,
  onOpenChange,
  secret,
  endpointUrl,
}: SecretRevealDialogProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(secret)
      setCopied(true)
      toast({
        title: 'Kopiert',
        description: 'Secret wurde in die Zwischenablage kopiert.',
      })
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast({
        title: 'Fehler',
        description: 'Secret konnte nicht kopiert werden.',
        variant: 'destructive',
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            Webhook-Secret
          </DialogTitle>
          <DialogDescription>
            Das Secret wird nur jetzt angezeigt und kann spaeter nicht mehr
            abgerufen werden. Speichern Sie es sicher.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="text-sm text-muted-foreground">
            Endpoint: <span className="font-mono">{endpointUrl}</span>
          </div>

          <div className="flex gap-2">
            <Input
              value={secret}
              readOnly
              className="font-mono text-sm"
            />
            <Button
              variant="outline"
              size="icon"
              onClick={handleCopy}
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>

          <div className="rounded-md bg-muted/50 p-3 text-sm space-y-2">
            <p className="font-medium">Verwendung:</p>
            <p className="text-muted-foreground">
              Verifizieren Sie eingehende Webhooks mit HMAC-SHA256.
              Der Signatur-Header heisst <code className="text-xs bg-muted px-1 rounded">X-Webhook-Signature</code>.
            </p>
            <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
{`import hmac, hashlib

def verify(payload, signature, secret):
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)`}
            </pre>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>
            Verstanden, Secret gespeichert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
