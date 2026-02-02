/**
 * TestNotificationButton Component
 *
 * Button zum Senden von Test-Benachrichtigungen.
 */

import { useState } from 'react';
import { Send, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import type { NotificationChannel } from '../types';
import { CHANNEL_LABELS } from '../types';

interface TestNotificationButtonProps {
  channel: NotificationChannel;
  onTest: (channel: NotificationChannel, message?: string) => Promise<void>;
  disabled?: boolean;
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'default' | 'sm' | 'lg';
}

type TestStatus = 'idle' | 'sending' | 'success' | 'error';

export function TestNotificationButton({
  channel,
  onTest,
  disabled = false,
  variant = 'outline',
  size = 'sm',
}: TestNotificationButtonProps) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState<TestStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string>('');

  const handleTest = async () => {
    setStatus('sending');
    setErrorMessage('');

    try {
      await onTest(channel, message || undefined);
      setStatus('success');
      setTimeout(() => {
        setOpen(false);
        setStatus('idle');
        setMessage('');
      }, 2000);
    } catch (error) {
      setStatus('error');
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Test-Benachrichtigung konnte nicht gesendet werden.'
      );
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setStatus('idle');
      setMessage('');
      setErrorMessage('');
    }
    setOpen(newOpen);
  };

  const channelLabel = CHANNEL_LABELS[channel];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant={variant} size={size} disabled={disabled}>
          <Send className="h-4 w-4 mr-1" />
          Test
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Test-Benachrichtigung senden</DialogTitle>
          <DialogDescription>
            Senden Sie eine Test-Benachrichtigung ueber {channelLabel}, um die
            Konfiguration zu ueberpruefen.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Custom Message */}
          <div className="space-y-2">
            <Label htmlFor="test-message">Nachricht (optional)</Label>
            <Input
              id="test-message"
              placeholder="Test-Nachricht eingeben..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={status === 'sending'}
            />
            <p className="text-sm text-muted-foreground">
              Leer lassen fuer Standard-Testnachricht.
            </p>
          </div>

          {/* Status Feedback */}
          {status === 'success' && (
            <Alert className="border-green-500/50 bg-green-500/10">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <AlertDescription>
                Test-Benachrichtigung wurde erfolgreich gesendet!
              </AlertDescription>
            </Alert>
          )}

          {status === 'error' && (
            <Alert variant="destructive">
              <XCircle className="h-4 w-4" />
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          )}

          {/* Channel-spezifische Hinweise */}
          {channel === 'sms' && (
            <Alert>
              <AlertDescription>
                <strong>Hinweis:</strong> SMS-Tests koennen Kosten verursachen.
                Stellen Sie sicher, dass Ihre Telefonnummer korrekt hinterlegt ist.
              </AlertDescription>
            </Alert>
          )}

          {channel === 'push' && (
            <Alert>
              <AlertDescription>
                <strong>Hinweis:</strong> Push-Benachrichtigungen erfordern eine
                Browser-Berechtigung. Falls keine Benachrichtigung erscheint,
                pruefen Sie die Browser-Einstellungen.
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleTest} disabled={status === 'sending'}>
            {status === 'sending' ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Wird gesendet...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Test senden
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default TestNotificationButton;
